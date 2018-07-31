################################################################################################
# Routing algorithm
###################################################################################################
import psycopg2
import random

# Processing Parameters

#database connection
db_conn = 'user=postgres password=postgres host=localhost dbname=eilat_routing'
conn=psycopg2.connect(db_conn)

#function to get one sample of each type
def createSample(types,seed):
    cur=conn.cursor()
    pts_selected = []
    for t in types:
        #get all points within region type
        cur.execute("""SELECT id FROM roads_vertices_pgr,(SELECT * FROM roi WHERE dn=%s) AS type_region WHERE ST_DWithin(type_region.geom,roads_vertices_pgr.the_geom,0.00025);""",[t])
        pts=cur.fetchall()

        #get single point for each type
        random.seed(seed)
        pts_selected.append(random.choice(pts)[0])
    cur.close()

    return pts_selected

#Parameters
#types of built-up
types = [11,12,13,21,22,23,31,32,33,41,42,43]
#maximum length (hours of survey * 10km/h)
max_l = 50
#max_l = 70
#start and end of route
#start_idx=2608

#nablus
#start_idx=1520
#rammallah
start_idx=36
#start_idx=2759
end_idx=start_idx
seed=42
#end_idx=78

#determine sample route
route_length = 0
dx = 0
route = {}
pts = []

#feedback
print('PGR_ROUTING ALGORITHM\n Using: {}\n region-types: {}\n maximum length: {}\n start_node:{}\n'.format(db_conn,types,max_l,start_idx))
print('!!!Dropping any previous routes on this database!!!\n')

#make copy of roads
cur=conn.cursor()
cur.execute('DROP TABLE IF EXISTS roads_copy;')
cur.execute('CREATE TABLE roads_copy AS (SELECT * FROM roads)')
#drop previous routes
cur.execute('DROP TABLE IF EXISTS  routing_result;')
cur.execute('CREATE TABLE routing_result(id integer,seq integer, cost double precision);')
cur.execute('DROP TABLE IF EXISTS route;')
cur.execute('CREATE TABLE route(id integer,seq integer, geom geometry);')
#commit changes
conn.commit()
cur.close()

#function to calculate added cost if edge revisted x times
#def addedCost(x):
#    return sum([(i-1)*1000 for i in range(1,x+1)])

#endless loop which will be broken once we exceed max_l
while True:
  print('Starting to generate sample route...\n')
  #reset cost values of roads for each new route
  cur=conn.cursor()
  cur.execute('DROP TABLE roads;')
  cur.execute('CREATE TABLE roads AS (SELECT * FROM roads_copy)')
  conn.commit()
  cur.close()

  #sample nodes for each region to construct route of (keeping previously selected ones)
  #alter random seed for each added set of sample points
  seed = seed+dx
  #store route determined before
  old_route = route
  #get sample points for region types (make sure points are unique)
  pts = list(set(pts+createSample(types,seed)))
  print('nr of nodes:{}\n'.format(len(pts)))
  all_pts=','.join(str(x) for x in list(set([start_idx]+pts+[end_idx])))
  #all_pts=set([start_idx]+pts+[end_idx])

  #get bird-fly-distance-optimized order of selected points
  subquery='SELECT CAST(id AS integer) ,ST_X(the_geom) AS x, ST_Y(the_geom) AS y FROM roads_vertices_pgr WHERE id IN ({}) ORDER BY id'.format(all_pts)
  query = "SELECT seq, id1, id2, round(cost::numeric, 5) AS cost FROM pgr_tsp('{}',{},{});".format(subquery,start_idx,end_idx)
  cur = conn.cursor()
  cur.execute(query)
  bird_tsp=cur.fetchall()
  cur.close()


  #create route for each pair of sample points using Djikstra algorithm
  nodes=[x[2] for x in bird_tsp]
  seq,node,edges,new_edges,cost=[],[],[],[],[]
  last_seq=0
  #n_unique=0
  all_edges=[]
  for i in range(len(nodes)-1):
      query = "SELECT seq,id1,id2,cost FROM pgr_dijkstra('SELECT id, source, target, cost ,reverse_cost FROM roads',{},{},true,true)".format(nodes[i],nodes[i+1])
      cur = conn.cursor()
      cur.execute(query)
      data = cur.fetchall()
      #remove last row which is just endpoint
      data = data[:-1]
      #make sequence additive and don't start a new for each part of the route
      seq = seq + [last_seq+x[0] for x in data]
      last_seq=seq[-1]+1
      #add passed nodes to route
      node = node + [x[1] for x in data]
      #determine newly passed edges
      new_edges = [x[2] for x in data if x[2] not in edges]
      edges = edges + [x[2] for x in data]
      #add cost of route
      cost = cost + [x[3] for x in data]
      #increase cost of newly used edges,i.e. avoid passing edges twice (if possible)
      if new_edges != []:
          used_edges=','.join([str(x) for x in new_edges])
          query = "UPDATE roads SET cost=cost+1000,reverse_cost=reverse_cost+1000 WHERE id IN ({})".format(used_edges)
          cur.execute(query)
          conn.commit()
      cur.close()
     # n_unique=n_unique+len(new_edges)

  #determine number of edges which are revisited along the route
  tup = [sorted([node[x],node[x+1]]) for x in range(0,len(node)-1)]
  #tup = [(x[0],x[1]) for x in tup]
  #d = {x:tup.count(x) for x in tup}
  tup2 = set([tuple(x) for x in tup])
  #nrr = sum([d[key]-1 for key in d.keys()])
  #too_much=0
  #for key in d.keys():
  #    too_much += addedCost(d[key])
  nrr = len(tup)-len(tup2)
  #nrr = len(edges)-n_unique
  #calculate route length in km corrected for the added sum_1_to_x((x-1)*1000m) per revisited edge
  #route_length = (sum(cost)-too_much)/1000
  route_length = (sum(cost)-nrr*1000)/1000
  dx = dx+1
  if route_length > max_l:
      print('Route determined with {} sample nodes, passing {} nodes where {} edges are revisited.\nTotal length {} km.'.format(len(pts),len(node),nrr,route_length))
      break
  else:
      print('Length of route: {}\n Aimed for length: {}\nGathering additional sample nodes\n'.format(route_length,max_l))
      #reset cost for used edges to original values

##get point geometries for nodes
route=[(node[i],seq[i],cost[i]) for i in range(len(node))]
#write route to db
cur = conn.cursor()
for x in route:
    query = "INSERT INTO routing_result(id,seq,cost) VALUES {}".format(x)
    cur.execute(query)
conn.commit()
cur= conn.cursor()
query="INSERT INTO route(id,seq,geom) SELECT rr.id,rr.seq,g.the_geom FROM routing_result AS rr LEFT OUTER JOIN (SELECT id,the_geom FROM roads_vertices_pgr) AS g ON rr.id=g.id"
cur.execute(query)
conn.commit()
cur.close()

#write edges to database as well
cur = conn.cursor()
cur.execute('DROP TABLE IF EXISTS route_edges;')
cur.execute('CREATE TABLE route_edges(id integer,geom geometry);')
query ="INSERT INTO route_edges(id,geom) SELECT id,geom FROM roads WHERE id in ({});".format(','.join([str(x) for x in edges]))
cur.execute(query)
conn.commit()
cur.close()

#write sample points to database
cur = conn.cursor()
cur.execute('DROP TABLE IF EXISTS sample_points;')
cur.execute('CREATE TABLE sample_points(id integer, sampled_node integer);')
for pt in pts:
    cur.execute("INSERT INTO sample_points(sampled_node) VALUES ({});".format(pt))
conn.commit()
cur.close()

#rewrite copy of roads to roads
cur=conn.cursor()
cur.execute('DROP TABLE roads;')
cur.execute('CREATE TABLE roads AS (SELECT * FROM roads_copy)')
conn.commit()
cur.close()
conn.close()
