

Convert GTFS info to OSM format to help integrate them in OpenStreetMap

usage:

    1) download and unzip a GTFS file into current folder
    
    2) execute

        ./gtfs_to_osm.py

            -> generate an AGENCY.osm file

    3) download all the stops in the wanted area, for instance with a request on https://overpass-turbo.eu/ :

            (
              node[public_transport=stop_position]({{bbox}});
              node[public_transport=platform]({{bbox}});
              node[highway=bus_stop]({{bbox}});
            );
            out meta;

    4) save it in a file, for instace stops.osm

    5) Add a line, for instance line 115 to the downloded stops.osm file:

        ./add-line.py stops.om 115

    6) Edit stops.osm in JOSM and fix any generated TODO

