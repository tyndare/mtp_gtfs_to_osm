#!/usr/bin/env python3

import sys
import csv
import json
import string
import os.path
import argparse
import datetime
from pprint import pprint
from collections import namedtuple,defaultdict

import gtfs_to_osm

from osm import OsmParser,OsmWriter,Node,Relation,Way


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

CHANGE_NAME = [
    ("Eglise", "Église"),
    ("Ecole", "École"),
    (" De ", " de "),
    (" Du ", " du "),
    ("-De-", "-de-"),
    ("-Du-", "-du-"),
]

def format_stop_name(name, route_type, agency):
    if agency == "HAUTE-GARONNE":
        if name.find(" - ") >=  0:
            city_name, stop_name = name.split(" - ", 1)
            name = stop_name + " " + capitalize_name(city_name)
    for v1,v2 in CHANGE_NAME:
        name = name.replace(v1,v2)
    return name

def capitalize_name(name):
    return "-".join(map(str.capitalize, name.split("-")))

def format_relation_name(route, stop_list, agency):
    prefix = gtfs_to_osm.route_type_name[route.route_type]
    return prefix + " " + route.route_short_name + ": " \
            + format_stop_name(stop_list[0].stop_name, route.route_type, agency) \
            + " → " \
            + format_stop_name(stop_list[-1].stop_name, route.route_type, agency)

def usage():
    print("USAGE:", sys.argv[0], "osm-stops.osm")

def add_todo_fixme(item, text):
    text = "TODO: " + text
    if text not in item.tags.get("fixme","").split(";"):
        item.attrs["action"] = "modify"
        if item.tags.get("fixme"):
            item.tags["fixme"] = text + ";" + item.tags["fixme"]
        else:
            item.tags["fixme"] = text


NORMALIZE_NAME = [
    (" - ", "-"),
]

def normalize_name(name):
    if name:
        for v1,v2 in NORMALIZE_NAME:
            name = name.replace(v1,v2)
        name = name.lower()
    return name

def name_ok(names, wanted_names):
    if type(names) not in (tuple, list):
        names = [names]
    if type(wanted_names) not in (tuple, list):
        wanted_names = [wanted_names]
    for name in map(normalize_name, names):
        if name:
            for wanted_name in map(normalize_name, wanted_names):
                if name == wanted_name \
                        or name == wanted_name + "-TAD" \
                        or wanted_name.startswith(name + " - ") \
                        or wanted_name.endswith(" - " + name) \
                        or name.startswith(wanted_name + " (") \
                        or name.endswith(" (" + wanted_name + ")"):
                    return True
    return False


def test_and_set(item, tag_name, tag_value):
    if item.tags.get(tag_name) != tag_value:
        item.attrs["action"] = "modify"
        item.tags[tag_name] = tag_value

def trip_comparison_key(list_of_stops):
    return (
        len(list_of_stops),
        len(gtfs.trips_by_list_of_stops[list_of_stops]))

def filter_printable(s):
    return ''.join(filter(lambda x: x in string.printable, s))

def remove_following_duplicate(from_list, key=lambda v:v):
    i=0
    previous = None
    while i<len(from_list):
        if key(from_list[i]) == previous:
            del(from_list[i])
        else:
            previous = key(from_list[i])
            i = i + 1

def get_or_add_stops_by_ref(osm_data, stop_list, all_stops, ref_attribute, route_type, agency):
    route_tag = gtfs_to_osm.route_type_route_tag[route_type]
    stops_by_ref = {}
    osm_node_by_ref = defaultdict(list)
    all_stop_refs = set([stop.stop_code for stop in all_stops])
    for stop in stop_list:
        stops_by_ref[stop.stop_code] = stop
    for node in osm_data.nodes.values():
        if ((node.tags.get("public_transport") == "stop_position")
                and (node.tags.get("highway") == "bus_stop")):
            node.attrs["action"] = "modify"
            del(node.tags["highway"])
        elif ((node.tags.get("highway") == "bus_stop")
                or (node.tags.get("public_transport") == "platform")):
            test_and_set(node, "public_transport", "platform")
            test_and_set(node, "highway", "bus_stop")
            ref = node.tags.get(ref_attribute)
            if ref:
                if ref in stops_by_ref:
                    osm_node_by_ref[ref].append(node)
                else:
                    if (ref_attribute != "ref") and (ref not in all_stop_refs):
                        add_todo_fixme(node, ref_attribute + " non trouvé dans les données de référence " + agency)
    for ref, node_list in list(osm_node_by_ref.items()):
        stop = stops_by_ref[ref]
        stop_name = format_stop_name(stop.stop_name, route_type, agency)
        best_distance = None
        best_node = None
        for node in node_list:
            distance = node.distance(Node(attrs={"lon": stop.stop_lon, "lat": stop.stop_lat}))
            if (best_distance is None) or (distance < best_distance):
                best_node = node
                best_distance = distance
            if len(node_list) > 1:
                add_todo_fixme(node, str(len(node_list)) + " stops avec le même" + ref_attribute)
            if distance > 100:
                add_todo_fixme(node, "à " + str(distance) + " m des données de référence " + agency)
            test_and_set(node, ref_attribute, ref)
            if stop.wheelchair_boarding == "1":
                if not node.tags.get("wheelchair"):
                    test_and_set(node, "wheelchair", "yes")
                elif node.tags.get("wheelchair") != "yes":
                    add_todo_fixme(node, "wheelchair != yes contrairement aux données de référence " + agency)
            elif stop.wheelchair_boarding == "2":
                if not node.tags.get("wheelchair"):
                    test_and_set(node, "wheelchair", "no")
                elif node.tags.get("wheelchair") != "no":
                    add_todo_fixme(node, "wheelchair != no contrairement aux données de référence " + agency)
            if not name_ok([node.tags.get("name"),
                            node.tags.get("alt_name"),
                            node.tags.get("short_name"),
                            node.tags.get("official_name"),
                            node.tags.get("name:" + ref_attribute),
                           ],
                           [stop_name, stop.stop_name]):
                add_todo_fixme(node, "name != " + stop_name)
        osm_node_by_ref[ref] = best_node

    for stop in stop_list:
        ref = stop.stop_code
        stop_name = format_stop_name(stop.stop_name, route_type, agency)
        if ref not in osm_node_by_ref:
            node = osm_data.create_node(
                attrs={
                    "lon": stop.stop_lon,
                    "lat": stop.stop_lat,
                    "action": "modify",
                },
                tags={
                    "name": stop_name,
                    "highway" : "bus_stop",
                    "public_transport": "platform",
                    route_tag: "yes",
                    ref_attribute: ref,
                    "source:" + ref_attribute: SOURCE_ATTRIBUTE_OF_AGENCY.get(agency,""),
                    "fixme": "TODO: arrêt importé à fusionner si déjà existante et/ou à vérifier",
                })
            if stop.wheelchair_boarding == "1":
                test_and_set(node, "wheelchair", "yes")
            elif stop.wheelchair_boarding == "2":
                test_and_set(node, "wheelchair", "no")
            osm_node_by_ref[ref] = node
    return osm_node_by_ref

def add_trip(gtfs, trip, route, list_of_stops_id, osm_data, start_date, end_date):
    osm_stop_by_ref = {}
    stop_list = [gtfs.stops[stop_id] for stop_id in list_of_stops_id]
    remove_following_duplicate(stop_list, key=lambda stop:stop.stop_code)
    agency = gtfs.agency[route.agency_id].agency_name
    name = format_relation_name(route, stop_list, agency)
    print("add trip", name)
    ref_attribute = REF_ATTRIBUTE_OF_AGENCY.get(agency, "ref")
    duration = gtfs.get_duration_from_list_of_stops(list_of_stops_id)
    interval = gtfs.get_interval_from_list_of_stops(list_of_stops_id, start_date=start_date, end_date=end_date)
    opening_hours = gtfs.get_opening_hours_from_list_of_stops(list_of_stops_id, start_date=start_date, end_date=end_date)
    route_tag = gtfs_to_osm.route_type_route_tag[route.route_type]
    colour_tag = "#" + route.route_color.upper()
    route_ref = gtfs.get_ref_from_list_of_stops(list_of_stops_id)

    osm_stop_by_ref = get_or_add_stops_by_ref(osm_data, stop_list, gtfs.stops.values(), ref_attribute, route.route_type, agency)

    rel = osm_data.create_relation(
        attrs={ "action":"modify"},
        tags={
            "name":name,
            "type":"route",
            "route":route_tag,
            "duration":duration,
            "opening_hours":opening_hours,
            "colour":colour_tag,
            "ref":route_ref,
            "public_transport:version" : "2",
            "fixme": "TODO: route importée à fusionner si déjà existante et/ou à vérifier",
            "from" : osm_stop_by_ref[stop_list[0].stop_code].tags.get("name",""),
            "to" : osm_stop_by_ref[stop_list[-1].stop_code].tags.get("name",""),
        })
    if NETWORK_OF_AGENCY.get(agency):
        rel.tags["network"] = NETWORK_OF_AGENCY[agency]
    for stop in stop_list:
        rel.add_member(osm_stop_by_ref[stop.stop_code], "platform")

def trip_comparison_key(gtfs, list_of_stops):
    return (
        len(list_of_stops),
        len(gtfs.trips_by_list_of_stops[list_of_stops]))

def add_line(gtfs, osm_data, line_ref, date):
    found = False
    start_date = date
    end_date = date + datetime.timedelta(days=7)
    for list_of_stops in sorted(gtfs.all_lists_of_stops, key=lambda s: trip_comparison_key(gtfs,s), reverse=True):
        if ((gtfs.get_end_date_from_list_of_stops(list_of_stops) >= start_date)
                and (gtfs.get_start_date_from_list_of_stops(list_of_stops) <= end_date)):
            trip_id_list = list(gtfs.trips_by_list_of_stops[list_of_stops])
            trip = gtfs.trips[trip_id_list[0]]
            route = gtfs.routes[trip.route_id]
            if route.route_short_name == line_ref:
                found = True
                add_trip(gtfs, trip, route, list_of_stops, osm_data, start_date, end_date)
    if not found:
        print("ERROR: no trip found with short_name =", line_ref, "at date", str(date))
        sys.exit(-1)

def parse_date(date_str):
    return datetime.datetime.strptime(date_str, '%Y-%m-%d').date()


def add_line_main():
    parser = argparse.ArgumentParser(description='Add GTFS line stops to OSM.')
    parser.add_argument('-g', "--gtfs", help="GTFS file", default=".")
    parser.add_argument('-o', "--output", help="output osm file")
    parser.add_argument('-d', "--date", help="date of trip",
                        type=parse_date,
                        default=datetime.date.today())
    parser.add_argument('osm_file')
    parser.add_argument('line_ref')
    args = parser.parse_args()
    print("Read GTFS in " + args.gtfs)
    gtfs = gtfs_to_osm.MyGTFS(args.gtfs)
    print("parse " + args.osm_file)
    osm_data = OsmParser().parse(args.osm_file)
    add_line(gtfs, osm_data, args.line_ref, args.date)
    output_file = args.output or args.osm_file
    print("write " + output_file)
    OsmWriter(osm_data).write_to_file(output_file)

if __name__ == '__main__':
    add_line_main()
