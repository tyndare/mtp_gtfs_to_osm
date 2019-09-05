#!/usr/bin/env python3


import os.path
import datetime
import urllib.request
from zipfile import ZipFile
from collections import namedtuple
from pprint import pprint

"""
Extract some GTFS info from Montpellier to help integrate them in OpenStreetMap
"""

# list_of_stops: J'utilise souvent une variable
#   nommée list_of_stops pour représenter une liste
#   d'arrêts constituant un itinéraire.


if not all([os.path.isfile(filename)
        for filename in
        ["stops.txt", "routes.txt", "trips.txt", "stop_times.txt", "calendar.txt"]]):
    url = "http://data.montpellier3m.fr/sites/default/files/ressources/TAM_MMM_GTFS.zip"
    filename = os.path.basename(url)
    print("download " + url)
    urllib.request.urlretrieve(url, filename)
    ZipFile(filename, "r").extractall()

def parse_csv(filename, typename):
    with open(filename) as f:
        lines = iter(f.readlines())
        fields_names = next(lines).strip().split(",")
        fields_names[0] = fields_names[0][1:]
        typeclass = namedtuple(typename, fields_names)
        return [
            typeclass(*fields)
            for fields in map(lambda s:map(
                lambda s: s.strip().replace('"',''),
                s.split(",")), lines)
        ]

stops = {stop.stop_id : stop for stop in parse_csv("stops.txt", "Stop")}
routes = {route.route_id : route for route in parse_csv("routes.txt", "Route")}
trips = {trip.trip_id : trip for trip in parse_csv("trips.txt", "Trip")}
stop_times = parse_csv("stop_times.txt", "StopTime")
services = {service.service_id : service for service in parse_csv("calendar.txt", "Calendar")}

stop_times_by_trip_id = {}
for stop_time in stop_times:
    if stop_time.trip_id not in stop_times_by_trip_id:
        stop_times_by_trip_id[stop_time.trip_id] = []
    stop_times_by_trip_id[stop_time.trip_id].append(stop_time)

def trip_stops_ids(trip_id):
    trip_stop_times = stop_times_by_trip_id[trip_id]
    trip_stop_times.sort(key=lambda stop_time:int(stop_time.stop_sequence))
    return tuple([stop_time.stop_id for stop_time in trip_stop_times])


trips_by_list_of_stops = {}
for trip in trips.values():
    trip_stops = trip_stops_ids(trip.trip_id)
    if trip_stops not in trips_by_list_of_stops:
        trips_by_list_of_stops [trip_stops] = set()
    trips_by_list_of_stops[trip_stops].add(trip.trip_id)

all_lists_of_stops = sorted(trips_by_list_of_stops.keys())

def get_ref_from_list_of_stops(list_of_stops):
    refs = set([
        routes[trips[trip_id].route_id].route_short_name
        for trip_id in trips_by_list_of_stops[list_of_stops]])
    return ";".join(sorted(refs))

def get_route_type(list_of_stops):
    route_types = set([
        routes[trips[trip_id].route_id].route_type
        for trip_id in trips_by_list_of_stops[list_of_stops]])
    return ";".join(sorted(route_types))

def get_name_from_list_of_stops(list_of_stops):
    names = set([
        routes[trips[trip_id].route_id].route_long_name
        for trip_id in trips_by_list_of_stops[list_of_stops]])
    return ";".join(sorted(names))

def get_headsign_from_list_of_stops(list_of_stops):
    headsigns = set([
        trips[trip_id].trip_headsign
        for trip_id in trips_by_list_of_stops[list_of_stops]])
    return ";".join(sorted(headsigns))

def parse_time(time_str):
    hours, minutes, seconds = map(int, time_str.split(":"))
    return datetime.timedelta(hours=hours, minutes=minutes, seconds=seconds)

def format_time(timedelta):
    hours = timedelta.seconds // 3600
    minutes = (timedelta.seconds // 60) % 60
    seconds = timedelta.seconds % 60
    return "{:02d}:{:02d}:{:02d}".format(hours,minutes,seconds)

week_days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

def is_trip_serviced_on_day(trip_id, day):
    service = services[trips[trip_id].service_id]
    return getattr(service, day) == "1"

def get_duration_from_list_of_stops(list_of_stops):
    durations = []
    for trip_id in trips_by_list_of_stops[list_of_stops]:
        trip_departure_time = min([
            parse_time(stop_time.departure_time)
            for stop_time in stop_times_by_trip_id[trip_id]])
        trip_arrival_time = max([
            parse_time(stop_time.arrival_time)
            for stop_time in stop_times_by_trip_id[trip_id]])
        durations.append((trip_arrival_time - trip_departure_time))
    total_duration = datetime.timedelta(0)
    for d in durations:
        total_duration = total_duration + d

    # j'ai le sentiment que durée moyenne du trajet n'est pas
    # représentative car:
    # - les moments où le bus vas vite c'est en général ou il a peu de voyageur
    # - les moment ou il vas lentement c'est en général ou il est blindé
    # Je pense qu'en moyenne plus de gens prennent le bus qand il est lent
    # que quand il est rapide.

    # Pour avoir un truc plus représentatif, je donne comme durée
    # la moyenne entre la durée moyenne et la durée maximale:

    mean_duration = total_duration / len(durations)
    max_duration = max(durations)
    duration = (mean_duration + max_duration) / 2
    return format_time(duration)

def get_interval_from_list_of_stops(list_of_stops):
    total_interval = datetime.timedelta(0)
    interval_count = 0
    for day in week_days:
        departure_times_of_day = sorted([
            min([
                parse_time(stop_time.departure_time)
                for stop_time in stop_times_by_trip_id[trip_id]])
            for trip_id in trips_by_list_of_stops[list_of_stops]
            if is_trip_serviced_on_day(trip_id, day)
            ])
        if len(departure_times_of_day) > 1:
            total_interval += departure_times_of_day[-1] - departure_times_of_day[0]
            interval_count += len(departure_times_of_day) - 1
    if interval_count:
        # retourne la moyenne, je ne sais pas si c'est représentatif
        return format_time(total_interval / interval_count)
    else:
        return ""

day_short_name = {
    "monday" : "Mo",
    "tuesday" : "Tu",
    "wednesday" : "We",
    "thursday" : "Tu",
    "friday" : "Fr",
    "saturday" : "Sa",
    "sunday" : "Su",
}

def get_opening_hours_from_list_of_stops(list_of_stops):
    """
    returne les heures entre le départ du premier service
    et l'arrivée du dernier service de chaque jour
    comme expliqué sur cette page:
        https://wiki.openstreetmap.org/wiki/Buses
    """
    opening_hours_by_day = {}
    for day in week_days:
        departure_times_of_day = sorted([
            min([
                parse_time(stop_time.departure_time)
                for stop_time in stop_times_by_trip_id[trip_id]])
            for trip_id in trips_by_list_of_stops[list_of_stops]
            if is_trip_serviced_on_day(trip_id, day)
            ])
        arrival_times_of_day = sorted([
            max([
                parse_time(stop_time.arrival_time)
                for stop_time in stop_times_by_trip_id[trip_id]])
            for trip_id in trips_by_list_of_stops[list_of_stops]
            if is_trip_serviced_on_day(trip_id, day)
            ])
        if departure_times_of_day and arrival_times_of_day:
            opening_hours_by_day[day] = \
                    format_time(departure_times_of_day[0])[:5] \
                    + "-" \
                    + format_time(arrival_times_of_day[-1])[:5]
        else:
            opening_hours_by_day[day] = None
    opening_hours_list = None
    for day in week_days:
        if opening_hours_by_day[day]:
            opening_hours_list = [[[day,day], opening_hours_by_day[day]]]
            previous_day = day
            break
    if opening_hours_list:
        for day in week_days[1:]:
            if opening_hours_by_day[day]:
                if opening_hours_by_day[day] == opening_hours_list[-1][1] \
                        and previous_day == opening_hours_list[-1][0][1]:
                    opening_hours_list[-1][0][1] = day
                else:
                    opening_hours_list.append([[day,day], opening_hours_by_day[day]])
            previous_day = day
    opening_hours = ";".join([
            (day_short_name[oh[0][0]] if oh[0][0] == oh[0][1]
             else day_short_name[oh[0][0]] + "-" + day_short_name[oh[0][1]])
            + " "
            + oh[1]
            for oh in opening_hours_list])
    return opening_hours

route_type_name = {
    "0" : "Tram",
    "1" : "Métro",
    "2" : "Train",
    "3" : "Bus",
    "4" : "Ferry",
    "5" : "Tram",
    "6" : "Téléphérique",
    "7" : "Funiculaire",
}
route_type_tag = {
    "0" : ("railway", "tram"),
    "1" : ("railway", "subway"),
    "2" : ("railway", "train"),
    "3" : ("highway", "service"),
    "4" : ("route", "ferry"),
    "5" : ("railway", "tram"),
    "6" : ("aerialway","cable_car"),
    "7" : ("railway", "funicular"),
}

def get_osm_name_from_list_of_stops(list_of_stops):
    route_type = get_route_type(list_of_stops)
    ref = get_ref_from_list_of_stops(list_of_stops)
    osm_name = route_type_name[route_type] \
            + " " + ref + ": " \
            + stops[list_of_stops[0]].stop_name \
            + " → " \
            + stops[list_of_stops[-1]].stop_name
    return osm_name

def write_osm_pseudo_ways(filename):
    print("write " + filename)
    f = open(filename, "w")

    f.write("<?xml version='1.0' encoding='UTF-8'?>\n")
    f.write("<osm version='0.6' upload='false' generator='mtp_gtfs_to_osm.py'>\n")


    id_count = -1
    stop_osm_id = {}

    for stop in stops.values():
        id_count = id_count - 1
        stop_osm_id[stop.stop_id] = id_count
        f.write("  <node id='{stop_id}' action='modify' visible='true' lat='{stop_lat}' lon='{stop_lon}'>\n".format(
            stop_id=stop_osm_id[stop.stop_id],
            stop_lat=stop.stop_lat,
            stop_lon=stop.stop_lon))
        f.write('    <tag k="highway" v="bus_stop" />\n')
        f.write('    <tag k="name" v="{0}" />\n'.format(stop.stop_name.replace('"','')))
        f.write('    <tag k="ref" v="{0}" />\n'.format(stop.stop_code))
        f.write("  </node>\n")


    for list_of_stops in all_lists_of_stops:
        id_count = id_count - 1
        route_type = get_route_type(list_of_stops)
        f.write("  <way id='{0}' action='modify' visible='true'>\n".format(id_count))
        f.write('    <tag k="name" v="{0}" />\n'.format(get_osm_name_from_list_of_stops(list_of_stops)))
        f.write('    <tag k="official_name" v="{0}" />\n'.format(get_name_from_list_of_stops(list_of_stops)))
        f.write('    <tag k="description" v="{0}" />\n'.format(get_headsign_from_list_of_stops(list_of_stops)))
        f.write('    <tag k="ref" v="{0}" />\n'.format(get_ref_from_list_of_stops(list_of_stops)))
        f.write('    <tag k="{0}" v="{1}" />\n'.format(*route_type_tag[route_type]))
        f.write('    <tag k="oneway" v="yes" />\n')
        f.write('    <tag k="duration" v="{0}" />\n'.format(get_duration_from_list_of_stops(list_of_stops)))
        f.write('    <tag k="interval" v="{0}" />\n'.format(get_interval_from_list_of_stops(list_of_stops)))
        f.write('    <tag k="opening_hours" v="{0}" />\n'.format(get_opening_hours_from_list_of_stops(list_of_stops)))
        for stop_id in list_of_stops:
            f.write("    <nd ref='{0}' />\n".format(stop_osm_id[stop_id]))
        f.write("  </way>\n")


    f.write("</osm>\n")
    f.close()


if __name__ == '__main__':
    write_osm_pseudo_ways("mtp_gtfs.osm")

