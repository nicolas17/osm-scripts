#!/usr/bin/python3

# Adds addr:street tags to interpolation ways
# Copyright (C) 2016 Nicolás Alvarez <nicolas.alvarez@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import io
import requests
import psycopg2
import re
from lxml import etree

boundary_relation_id = 5970249 # Acevedo

conn = psycopg2.connect("dbname=argentina")
cur = conn.cursor()

cur.execute("SELECT ST_Extent(ST_Transform(way, 4326)) FROM planet_osm_polygon WHERE osm_id=%s", (-boundary_relation_id,))
(boxtext,) = cur.fetchone()
match = re.match(r'BOX\((-?[0-9.]+) (-?[0-9.]+),(-?[0-9.]+) (-?[0-9.]+)\)$', boxtext)
bbox = [float(c) for c in match.groups()]

map_req = requests.get("https://api.openstreetmap.org/api/0.6/map", params={'bbox': ','.join(str(coord) for coord in bbox)})

ways={}
nodes={}

xml = etree.parse(io.BytesIO(map_req.content))
for obj in xml.getroot():
    if obj.tag in ('bounds','relation'):
        pass
    elif obj.tag == 'node':
        nodes[int(obj.attrib['id'])] = obj
    elif obj.tag == 'way':
        ways[int(obj.attrib['id'])] = obj
    else:
        raise RuntimeError("Unexpected element %s".format(obj.tag))

xml.write(open("map-orig.xml","wb"))
cur.execute('''
SELECT street.osm_id street_id, street.name, interp.osm_id interp_id, interp."addr:interpolation", interp."addr:street"
FROM
    planet_osm_line street,
    planet_osm_line interp,
    planet_osm_polygon boundary
WHERE
    boundary.osm_id = %s
    AND ST_Contains(boundary.way, interp.way)
    AND ST_Intersects(boundary.way, street.way)
    AND ST_Contains(ST_Buffer(street.way, 15), interp.way)
    AND interp."addr:interpolation" IS NOT NULL
    AND interp."addr:street" IS NULL
    AND street.highway IS NOT NULL
''', [-boundary_relation_id])

for row in cur:
    street_id, name, interp_id, interp_type, interp_street = row
    assert interp_street is None
    if name is None:
        print("Street {} has no name, ignoring {} interp way {}".format(street_id, interp_type, interp_id))
        continue
    interp_way = ways[interp_id]
    interp_node_ids = [int(elem.attrib['ref']) for elem in interp_way if elem.tag == 'nd']
    interp_nodes = [nodes[node_id] for node_id in interp_node_ids]
    for node in interp_nodes:
        if any(elem.tag == 'tag' and elem.attrib['k'] == 'addr:housenumber' for elem in node):
            node.append(etree.Element("tag", attrib={"k":"addr:street", "v":name}))
            node.attrib['action']='modify'

    for elem in interp_way:
        if elem.tag == 'tag' and elem.attrib['k'] == 'addr:street':
            interp_way.remove(elem)
            interp_way.attrib['action'] = 'modify'


xml.write(open("map-modif.xml", "wb"))

