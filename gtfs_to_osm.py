#!/usr/bin/env python3

import io
import csv
import sys
import string
import os.path
import datetime
import urllib.request
from zipfile import ZipFile
from collections import namedtuple, defaultdict
from pprint import pprint


"""
Extract some GTFS info to help integrate them in OpenStreetMap
"""

# list_of_stops: J'utilise souvent une variable
#   nommée list_of_stops pour représenter une liste
#   d'arrêts constituant un itinéraire.

MIN_DATE=datetime.date.today()
MAX_DATE=MIN_DATE + datetime.timedelta(days=14)

REF_ATTRIBUTE_OF_AGENCY = {
    "Tisséo" : "ref:FR:Tisséo",
    "HAUTE-GARONNE" : "ref:FR:aec31",
}
SOURCE_ATTRIBUTE_OF_AGENCY = {
    "Tisséo" : "Tisséo",
    "HAUTE-GARONNE" : "Conseil Départemental de Haute-Garonne",
}

NETWORK_OF_AGENCY = {
    "HAUTE-GARONNE" : "Réseau Arc-en-Ciel",
    "Tisséo" : "fr_tisseo",
    "TAM": "TaM",
}

week_days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

class MyGTFS(object):
    def __init__(self, path="."):
        if os.path.isfile(path):
            zip_file = ZipFile(path)
            open_file = lambda filename: io.TextIOWrapper(zip_file.open(filename), encoding="utf-8")
        else:
            assert os.path.isdir(path)
            open_file = lambda filename: open(os.path.join(path, filename))
        self.stops = {stop.stop_id : stop for stop in parse_csv(open_file("stops.txt"), "Stop")}
        self.routes = {route.route_id : route for route in parse_csv(open_file("routes.txt"), "Route")}
        self.trips = {trip.trip_id : trip for trip in parse_csv(open_file("trips.txt"), "Trip")}
        self.stop_times = parse_csv(open_file("stop_times.txt"), "StopTime")
        try:
            self.services = {service.service_id : service for service in parse_csv(open_file("calendar.txt"), "Calendar")}
        except Exception as e:
            print(e)
            self.services = {}
        self.agency = {agency.agency_id : agency for agency in parse_csv(open_file("agency.txt"), "Agency")}
        self.shapes = {}
        try:
            for point in parse_csv(open_file("shapes.txt"), "Shape"):
                if point.shape_id not in self.shapes:
                    self.shapes[point.shape_id] = []
                self.shapes[point.shape_id].append(point)
        except:
            pass
        for shape in self.shapes.values():
            shape.sort(key=lambda point:int(point.shape_pt_sequence))

        self.stop_times_by_trip_id = {}
        for stop_time in self.stop_times:
            if stop_time.trip_id not in self.stop_times_by_trip_id:
                self.stop_times_by_trip_id[stop_time.trip_id] = []
            self.stop_times_by_trip_id[stop_time.trip_id].append(stop_time)
        for stop_time_list in self.stop_times_by_trip_id.values():
            stop_time_list.sort(key=lambda stop_time:int(stop_time.stop_sequence))

        self.trips_by_list_of_stops = {}
        for trip in self.trips.values():
            trip_stops = self.trip_stops_ids(trip.trip_id)
            if trip_stops not in self.trips_by_list_of_stops:
                self.trips_by_list_of_stops [trip_stops] = set()
            self.trips_by_list_of_stops[trip_stops].add(trip.trip_id)

        self.all_lists_of_stops = sorted(self.trips_by_list_of_stops.keys())

    def trip_stops_ids(self, trip_id):
        trip_stop_times = self.stop_times_by_trip_id[trip_id]
        return tuple([stop_time.stop_id for stop_time in trip_stop_times])

    def get_ref_from_list_of_stops(self, list_of_stops):
        refs = set([
            self.routes[self.trips[trip_id].route_id].route_short_name
            for trip_id in self.trips_by_list_of_stops[list_of_stops]])
        return ";".join(sorted(refs))

    def get_route_type(self, list_of_stops):
        route_types = set([
            self.routes[self.trips[trip_id].route_id].route_type
            for trip_id in self.trips_by_list_of_stops[list_of_stops]])
        return ";".join(sorted(route_types))

    def get_agency(self, list_of_stops):
        agencies_name = set([
            self.agency[self.routes[self.trips[trip_id].route_id].agency_id].agency_name
            for trip_id in self.trips_by_list_of_stops[list_of_stops]])
        return ";".join(sorted(agencies_name))

    def get_shape_route_type(self, shape_id):
        route_types = set([
            self.routes[trip.route_id].route_type
            for trip in self.trips.values() if trip.shape_id == shape_id])
        return ";".join(sorted(route_types))

    def get_route_colour(self, list_of_stops):
        route_colours = set([
            self.routes[self.trips[trip_id].route_id].route_type
            for trip_id in self.trips_by_list_of_stops[list_of_stops]])
        return ";".join(sorted(route_colours))

    def get_name_from_list_of_stops(self, list_of_stops):
        names = set([
            self.routes[self.trips[trip_id].route_id].route_long_name
            for trip_id in self.trips_by_list_of_stops[list_of_stops]])
        return ";".join(sorted(names))

    def get_headsign_from_list_of_stops(self, list_of_stops):
        headsigns = set([
            self.trips[trip_id].trip_headsign
            for trip_id in self.trips_by_list_of_stops[list_of_stops]])
        return ";".join(sorted(headsigns))

    def get_services_ids_from_list_of_stops(self, list_of_stops):
        return sorted(set([
            self.trips[trip_id].service_id
            for trip_id in self.trips_by_list_of_stops[list_of_stops]]))

    def get_start_date_from_list_of_stops(self, list_of_stops):
        services_list = [self.services[sid] for sid in self.get_services_ids_from_list_of_stops(list_of_stops) if sid in self.services]
        if len(services_list):
            return min([parse_date(service.start_date) for service in services_list])
        else:
            return datetime.date.today()

    def get_end_date_from_list_of_stops(self, list_of_stops):
        services_list = [self.services[sid] for sid in self.get_services_ids_from_list_of_stops(list_of_stops) if sid in self.services]
        if len(services_list):
            return max([parse_date(service.start_date) for service in services_list])
        else:
            return datetime.date.today()

    def is_trip_serviced_on_day(self, trip_id, day, start_date=MIN_DATE, end_date=MAX_DATE):
        service_id = self.trips[trip_id].service_id
        if service_id in self.services:
            service = self.services[self.trips[trip_id].service_id]
            return (getattr(service, day)) == "1" \
                and parse_date(service.start_date) <= end_date \
                and parse_date(service.end_date) >= start_date
        else:
            return True

    def get_duration_from_list_of_stops(self, list_of_stops, date=None):
        durations = []
        for trip_id in self.trips_by_list_of_stops[list_of_stops]:
            trip_departure_time = min([
                parse_time(stop_time.departure_time)
                for stop_time in self.stop_times_by_trip_id[trip_id]])
            trip_arrival_time = max([
                parse_time(stop_time.arrival_time)
                for stop_time in self.stop_times_by_trip_id[trip_id]])
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

    def get_interval_from_list_of_stops(self, list_of_stops, start_date=MIN_DATE, end_date=MAX_DATE):
        total_interval = datetime.timedelta(0)
        interval_count = 0
        for day in week_days:
            #print()
            #print(day)
            departure_times_of_day = sorted([
                min([
                    parse_time(stop_time.departure_time)
                    for stop_time in self.stop_times_by_trip_id[trip_id]])
                for trip_id in self.trips_by_list_of_stops[list_of_stops]
                if self.is_trip_serviced_on_day(trip_id, day, start_date, end_date)
                ])
            if len(departure_times_of_day) > 1:
                total_interval += departure_times_of_day[-1] - departure_times_of_day[0]
                interval_count += len(departure_times_of_day) - 1
                #for time in departure_times_of_day:
                #    print(time)
                #last_interval_start = departure_times_of_day[0]
                #last_interval = departure_times_of_day[1] - departure_times_of_day[0]
                #previous_time  = departure_times_of_day[1]
                #for time in departure_times_of_day[2:]:
                #    interval = time - previous_time
                #    if interval != last_interval:
                #        print(last_interval, "@", last_interval_start ,"-", previous_time)
                #        last_interval = interval
                #        last_interval_start = previous_time
                #    previous_time = time
                #print(last_interval, "@", last_interval_start ,"-", previous_time)

        if interval_count:
            # retourne la moyenne, je ne sais pas si c'est représentatif
            return format_time(total_interval / interval_count), None
        else:
            return None, None

    def get_opening_hours_from_list_of_stops(self, list_of_stops, start_date=MIN_DATE, end_date=MAX_DATE):
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
                    for stop_time in self.stop_times_by_trip_id[trip_id]])
                for trip_id in self.trips_by_list_of_stops[list_of_stops]
                if self.is_trip_serviced_on_day(trip_id, day, start_date, end_date)
                ])
            arrival_times_of_day = sorted([
                max([
                    parse_time(stop_time.arrival_time)
                    for stop_time in self.stop_times_by_trip_id[trip_id]])
                for trip_id in self.trips_by_list_of_stops[list_of_stops]
                if self.is_trip_serviced_on_day(trip_id, day, start_date, end_date)
                ])
            if departure_times_of_day:# and arrival_times_of_day:
                opening_hours_by_day[day] = \
                        format_time(departure_times_of_day[0])[:5] \
                        + "-" \
                        + format_time(departure_times_of_day[-1])[:5]
                        #+ format_time(arrival_times_of_day[-1])[:5]
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
            # Use coma "," separator for opening hours because they may pass the end
            # of the day and then overlap the following days.
            opening_hours = ";".join([
                    (day_short_name[oh[0][0]] if oh[0][0] == oh[0][1]
                    else day_short_name[oh[0][0]] + "-" + day_short_name[oh[0][1]])
                    + " "
                    + oh[1]
                    for oh in opening_hours_list])
            return opening_hours + ";May 1 off"
        else:
            return "off"
    def get_osm_name_from_list_of_stops(self, list_of_stops, prefix="", extension="", only_to=False):
        route_type = self.get_route_type(list_of_stops)
        ref = self.get_ref_from_list_of_stops(list_of_stops)
        osm_name = route_type_name[route_type] \
                + " " + prefix + ref + extension + ": "
        if only_to:
            osm_name = osm_name + only_to + self.stops[list_of_stops[-1]].stop_name
        else:
            osm_name = osm_name \
                + (self.stops[list_of_stops[0]].stop_name if list_of_stops[0] in self.stops else "?")\
                + " → " \
                + (self.stops[list_of_stops[-1]].stop_name if list_of_stops[-1] in self.stops else "?")
        return osm_name

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
route_type_way_tag = {
    "0" : ("railway", "tram"),
    "1" : ("railway", "subway"),
    "2" : ("railway", "train"),
    "3" : ("highway", "service"),
    "4" : ("route", "ferry"),
    "5" : ("railway", "tram"),
    "6" : ("aerialway", "cable_car"),
    "7" : ("railway", "funicular"),
}
route_type_route_tag = {
    "0" : "tram",
    "1" : "subway",
    "2" : "train",
    "3" : "bus",
    "4" : "ferry",
    "5" : "tram",
    "6" : "cable_car",
    "7" : "funicular",
}

day_short_name = {
    "monday" : "Mo",
    "tuesday" : "Tu",
    "wednesday" : "We",
    "thursday" : "Th",
    "friday" : "Fr",
    "saturday" : "Sa",
    "sunday" : "Su",
}


def parse_date(date_str):
    return datetime.date(
        year=int(date_str[0:4]),
        month=int(date_str[4:6]),
        day=int(date_str[6:8]),
    )

def parse_time(time_str):
    if time_str:
        hours, minutes, seconds = map(int, time_str.split(":"))
        return datetime.timedelta(hours=hours, minutes=minutes, seconds=seconds)
    else:
        return datetime.timedelta(hours=0, minutes=0, seconds=0)


def format_time(timedelta):
    hours = timedelta.seconds // 3600
    minutes = (timedelta.seconds // 60) % 60
    seconds = timedelta.seconds % 60
    return "{:02d}:{:02d}:{:02d}".format(hours,minutes,seconds)

def format_date(date):
    return "{:04d}-{:02d}-{:02d}".format(date.year, date.month, date.day)


def write_osm_pseudo_ways(gtfs, agency, osm_filename):
    print("write " + osm_filename)
    f = open(osm_filename, "w")

    f.write("<?xml version='1.0' encoding='UTF-8'?>\n")
    f.write("<osm version='0.6' upload='never' generator='%s'>\n" % (sys.argv[0],))


    id_count = -1
    stop_osm_id = {}

    for stop in gtfs.stops.values():
        id_count = id_count - 1
        stop_osm_id[stop.stop_id] = id_count
        f.write("  <node id='{stop_id}' action='modify' visible='true' lat='{stop_lat}' lon='{stop_lon}'>\n".format(
            stop_id=id_count,
            stop_lat=stop.stop_lat,
            stop_lon=stop.stop_lon))
        f.write('    <tag k="highway" v="bus_stop" />\n')
        f.write('    <tag k="public_transport" v="platform" />\n')
        f.write('    <tag k="bus" v="yes" />\n')
        f.write('    <tag k="source" v="{0}" />\n'.format(SOURCE_ATTRIBUTE_OF_AGENCY.get(agency.agency_name,"")))
        f.write('    <tag k="source:date" v="{0}" />\n'.format(MIN_DATE))
        f.write('    <tag k="name" v="{0}" />\n'.format(stop.stop_name.replace('"','')))
        f.write('    <tag k="stop_id" v="{0}" />\n'.format(stop.stop_id))
        f.write('    <tag k="ref" v="{0}" />\n'.format(stop.stop_code))
        f.write('    <tag k="{0}" v="{1}" />\n'.format(REF_ATTRIBUTE_OF_AGENCY.get(agency.agency_name, "ref"), stop.stop_code))
        f.write("  </node>\n")
        #stop_pos_lon=str(stop.stop_lon)
        #stop_pos_lat=str(float(stop.stop_lat)+ 0.00001)
        #id_count = id_count - 1
        #f.write("  <node id='{stop_id}' action='modify' visible='true' lat='{stop_pos_lat}' lon='{stop_pos_lon}'>\n".format(
        #    stop_id=id_count,
        #    stop_pos_lat=stop_pos_lat,
        #    stop_pos_lon=stop_pos_lon))
        #f.write('    <tag k="name" v="{0}" />\n'.format(stop.stop_name.replace('"','')))
        #f.write('    <tag k="public_transport" v="stop_position" />\n')
        #f.write('    <tag k="bus" v="yes" />\n')
        #f.write('    <tag k="source" v="extrapolation" />\n')
        #f.write("  </node>\n")


    osm_node_by_lon_lat = {}
    way_ids_by_shape_id = defaultdict(list)
    shape_ids_by_node_couple = defaultdict(set)
    way_id_by_node_couple = {}
    for shape_id, shape in gtfs.shapes.items():
        last_point = None
        for point in shape:
            lon_lat = (float(point.shape_pt_lon), float(point.shape_pt_lat))
            if lon_lat in osm_node_by_lon_lat:
                node_id = osm_node_by_lon_lat[lon_lat]
            else:
                id_count = id_count - 1
                osm_node_by_lon_lat[lon_lat] = id_count
                f.write("  <node id='{node_id}' action='modify' visible='true' lat='{lat}' lon='{lon}' />\n".format(
                    node_id=id_count,
                    lat=point.shape_pt_lat,
                    lon=point.shape_pt_lon))
                node_id = id_count
            if last_point:
                last_lon_lat = (float(last_point.shape_pt_lon), float(last_point.shape_pt_lat))
                last_node_id = osm_node_by_lon_lat[last_lon_lat]
                shape_ids_by_node_couple[(last_node_id, node_id)].add(shape_id)
                shape_ids_by_node_couple[(node_id, last_node_id)].add(shape_id)
            last_point = point
    for shape_id, shape in gtfs.shapes.items():
        route_type = gtfs.get_shape_route_type(shape_id)
        last_point = None
        last_shape_ids = None
        way_open = False
        way_ids = way_ids_by_shape_id[shape_id]
        for point in shape:
            lon_lat = (float(point.shape_pt_lon), float(point.shape_pt_lat))
            node_id = osm_node_by_lon_lat[lon_lat]
            if last_point:
                last_lon_lat = (float(last_point.shape_pt_lon), float(last_point.shape_pt_lat))
                last_node_id = osm_node_by_lon_lat[last_lon_lat]
                if (last_node_id, node_id) in way_id_by_node_couple:
                    way_id = way_id_by_node_couple[(last_node_id, node_id)]
                else:
                    shape_ids = shape_ids_by_node_couple[(last_node_id, node_id)]
                    if shape_ids == last_shape_ids:
                        # keep the same way_id as previous one
                        f.write("    <nd ref='{0}' />\n".format(node_id))
                    else:
                        last_shape_ids = shape_ids
                        if way_open:
                            f.write("  </way>\n")
                        else:
                            way_open = True
                        id_count = id_count - 1
                        way_id = id_count
                        f.write("  <way id='{0}' action='modify' visible='true'>\n".format(way_id))
                        f.write('    <tag k="{0}" v="{1}" />\n'.format(*route_type_way_tag[route_type]))
                        f.write("    <nd ref='{0}' />\n".format(last_node_id))
                        f.write("    <nd ref='{0}' />\n".format(node_id))
                    way_id_by_node_couple[(last_node_id, node_id)] = way_id
                    way_id_by_node_couple[(node_id, last_node_id)] = way_id

                if (len(way_ids) == 0) or (way_ids[-1] != way_id):
                    way_ids.append(way_id)
            last_point = point
        if way_open:
            f.write("  </way>\n")

    route_master_routes = defaultdict(list)
    route_master_name = {}
    route_master_tag = {}
    route_master_agency = {}
    for list_of_stops in gtfs.all_lists_of_stops:
        id_count = id_count - 1
        ref = gtfs.get_ref_from_list_of_stops(list_of_stops)
        route_type = gtfs.get_route_type(list_of_stops)
        route_name = gtfs.get_osm_name_from_list_of_stops(list_of_stops)
        route_tag = route_type_route_tag[route_type]
        official_name = gtfs.get_name_from_list_of_stops(list_of_stops)
        route_master_name[ref] = route_name.split(":")[0] + ": " + official_name
        route_master_tag[ref] = route_tag
        route_master_agency[ref] = gtfs.get_agency(list_of_stops)
        route_master_routes[ref].append(id_count)
        interval, interval_conditional = gtfs.get_interval_from_list_of_stops(list_of_stops)
        f.write("  <relation id='{0}' action='modify' visible='true'>\n".format(id_count))
        f.write('    <tag k="name" v="{0}" />\n'.format(route_name))
        f.write('    <tag k="official_name" v="{0}" />\n'.format(official_name))
        f.write('    <tag k="description" v="{0}" />\n'.format(gtfs.get_headsign_from_list_of_stops(list_of_stops)))
        f.write('    <tag k="ref" v="{0}" />\n'.format(ref))
        f.write('    <tag k="type" v="route" />\n')
        f.write('    <tag k="route" v="{0}" />\n'.format(route_tag))
        f.write('    <tag k="oneway" v="yes" />\n')
        f.write('    <tag k="duration" v="{0}" />\n'.format(gtfs.get_duration_from_list_of_stops(list_of_stops)))
        f.write('    <tag k="start_date" v="{0}" />\n'.format(format_date(gtfs.get_start_date_from_list_of_stops(list_of_stops))))
        f.write('    <tag k="end_date" v="{0}" />\n'.format(format_date(gtfs.get_end_date_from_list_of_stops(list_of_stops))))
        f.write('    <tag k="operator" v="{0}" />\n'.format(gtfs.get_agency(list_of_stops)))
        f.write('    <tag k="public_transport:version" v="2" />\n')
        missing_stops = []
        if interval:
            f.write('    <tag k="interval" v="{0}" />\n'.format(interval))
        if interval_conditional:
            f.write('    <tag k="interval" v="{0}" />\n'.format(interval_conditional))
        f.write('    <tag k="opening_hours" v="{0}" />\n'.format(gtfs.get_opening_hours_from_list_of_stops(list_of_stops)))
        for stop_id in list_of_stops:
            if stop_id in stop_osm_id:
                f.write("    <member type='node' role='platform' ref='{0}' />\n".format(stop_osm_id[stop_id]))
            else:
                missing_stops.append(stop_id)
                print("ERROR: stop_id " + stop_id + " referenced but not found in GTFS stops.txt")
        try:
            for shape_id in set([gtfs.trips[trip_id].shape_id for trip_id in gtfs.trips_by_list_of_stops[list_of_stops]]):
                for way_id in way_ids_by_shape_id[shape_id]:
                    f.write("    <member type='way' role='' ref='{0}' />\n".format(way_id))
        except:
            pass
        if missing_stops:
            f.write('    <tag k="fixme" v="{0}" />\n'.format("missing stops " + " ".join(missing_stops)))
        f.write("  </relation>\n")

    for ref, name in route_master_name.items():
        id_count = id_count - 1
        f.write("  <relation id='{0}' action='modify' visible='true'>\n".format(id_count))
        f.write('    <tag k="type" v="route_master" />\n')
        f.write('    <tag k="route_master" v="{0}" />\n'.format(route_master_tag[ref]))
        f.write('    <tag k="name" v="{0}" />\n'.format(name))
        f.write('    <tag k="ref" v="{0}" />\n'.format(ref))
        f.write('    <tag k="operator" v="{0}" />\n'.format(route_master_agency[ref]))
        for route_id in route_master_routes[ref]:
            f.write("    <member type='relation' role='' ref='{0}' />\n".format(route_id))
        f.write("  </relation>\n")




    f.write("</osm>\n")
    f.close()


def parse_csv(f, typename):
    rows = iter(csv.reader(f))
    fields_names = list(map(filter_printable, next(rows)))
    typeclass = namedtuple(typename, fields_names)
    return [
        typeclass(*fields)
        for fields in rows]

def filter_printable(s):
    return ''.join(filter(lambda x: x in string.printable, s))

if __name__ == '__main__':
    if len(sys.argv) > 2:
        print("ERROR: too many arguments")
    elif len(sys.argv) == 2:
        path = sys.argv[1]
    else:
        path = "."
    gtfs = MyGTFS(path)
    osm_filename = "-".join([agency.agency_name for agency in gtfs.agency.values()]) + ".osm"
    write_osm_pseudo_ways(gtfs, list(gtfs.agency.values())[0], osm_filename)

