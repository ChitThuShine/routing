#make sure that streets topology is well defined! use e.g. GRASS v.clean!!!


#create routing database and extensions
psql --user postgres
DROP DATABASE IF EXISTS eilat_routing;
CREATE DATABASE eilat_routing;
\c eilat_routing
CREATE EXTENSION postgis;
CREATE EXTENSION pgrouting;
CREATE EXTENSION postgis_topology;
\q

#write osm street network to database extracted in qgis and cleaned
shp2pgsql -s 32636:4326 eilat_streets.shp ways > eilat_streets.sql

#write ROI (built-up) to postgresql
shp2pgsql -s 32636:4326 eilat_simple_types.shp roi > eilat_ROI.sql


psql --user postgres --db eilat_routing
\i eilat_streets.sql
\i eilat_ROI.sql

---remove waterways&admin boundarie from osm lines
DELETE FROM ways WHERE other_tags LIKE '%admin%';
DELETE FROM ways WHERE waterway <> '';
DELETE FROM ways WHERE barrier <> '';
DELETE FROM ways WHERE other_tags LIKE '%bicycle%';
DELETE FROM ways WHERE other_tags LIKE '%Trail%';
DELETE FROM ways WHERE other_tags LIKE '%foot%';
DELETE FROM ways WHERE other_tags LIKE '%seamark%';
DELETE FROM ways WHERE highway LIKE '%footway%';
DELETE FROM ways WHERE highway LIKE '%pedestrian%';
DELETE FROM ways WHERE highway LIKE '%track%';
DELETE FROM ways WHERE highway LIKE '%path%';
DELETE FROM ways WHERE man_made LIKE '%pier%';
DELETE FROM ways WHERE other_tags LIKE '%natural%';
DELETE FROM ways WHERE other_tags LIKE '%ferry%';
DELETE FROM ways WHERE other_tags LIKE '%boat%';
DELETE FROM ways WHERE other_tags LIKE '%maritime%';
DELETE FROM ways WHERE other_tags LIKE '%aeroway%';
DELETE FROM ways WHERE other_tags LIKE '%Military%';


---CREATE postgis topology
SELECT topology.CreateTopology('ways_topo', 4326);
SELECT topology.AddTopoGeometryColumn('ways_topo', 'public', 'ways', 'topo_geom', 'LINESTRING');
--simplify geometry on the fly
UPDATE ways SET geom=ST_MULTI(ST_SimplifyPreserveTopology(geom,0.00001));
UPDATE ways SET topo_geom = topology.toTopoGeom(geom, 'ways_topo', 1, 0.000001);


---Use postgis topology to create routable streetnetwork (spatial join osm with topology)
CREATE TABLE roads(id integer,geom geometry, tags character varying(254));
INSERT INTO roads SELECT t.edge_id,t.geom,o.other_tags FROM ways_topo.edge_data AS t,ways AS o WHERE ST_WITHIN(t.geom,o.geom);
---add source and target column
ALTER TABLE roads ADD COLUMN "source" integer;
ALTER TABLE roads ADD COLUMN "target" integer;

---run topology function
SELECT pgr_createTopology('roads', 0.00001, 'geom', 'id');
---check graph
select pgr_analyzegraph('roads', 0.000001, 'geom','id');

--In case: identify isolated segments 
--SELECT * FROM roads a, roads_vertices_pgr b, roads_vertices_pgr c WHERE a.source=b.id AND b.cnt=1 AND a.target=c.id AND c.cnt=1;
--





---Create cost column (length) and reverse cost column
ALTER TABLE roads ADD COLUMN "cost" double precision;
ALTER TABLE roads ADD COLUMN "reverse_cost" double precision;
------add segment length as cost value
UPDATE roads SET cost=ST_Length(geom,true);
------make cost of non usable roads high
UPDATE roads SET cost=1000000 WHERE tags LIKE '%"motor_vehicle"=>"no"%';
------add reverse cost 
UPDATE roads SET reverse_cost=cost;
------make reverse_cost high for oneway streets
UPDATE roads SET reverse_cost=1000000 WHERE tags LIKE '%"oneway"=>"yes"%';

---Add result tables
CREATE TABLE routing_result(id integer,seq integer, cost double precision);
CREATE TABLE route(id integer,seq integer, geom geometry);

---run python  routine routing.py to determine sample route
