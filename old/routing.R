#routing
library(RPostgreSQL)

drv <- dbDriver("PostgreSQL")
con <- dbConnect(drv, dbname="madaba_routing",host="localhost",port=5432,user="postgres",password="postgres")

#function to get 1 pt for each region type from the vertices of streetnetwork
createSample <- function(types,seed){
  pts_selected <- c()
  for (t in types){
    #get all points within region type
    pts<-dbGetQuery(con,paste('SELECT id 
                            FROM roads_vertices_pgr,(SELECT * FROM roi WHERE cat=',toString(t),') AS type_region 
                            WHERE ST_Contains(type_region.geom,roads_vertices_pgr.the_geom);',sep=''))  
    
    #get single point for each type
    set.seed(seed)
    pts_selected <- append(pts_selected,sample(pts$id,1))
  }
  return(pts_selected)
}

#Parameters
#types of built-up
types <- c(11,12,13,21,22,23,31,32,33)
#maximum length (hours of survey * 10km/h)
max_l = 50
#start and end of route
start_idx=1971
end_idx=1971

#determine sample route
route_length <- 0
x <- 0
route <- c()
pts <- c()

#endless loop which will be broken once we exceed max_l
while (TRUE){
  seed <- 42+x
  #store route determined before
  old_route <- route
  #get sample points for region types
  pts <- unique(append(pts,createSample(types,seed)))
  end_idx <- pts[length(pts)]
  #get bird fly distance optimized order of selected points
  bird_tsp<- dbGetQuery(con,paste("SELECT seq, id1, id2, round(cost::numeric, 5) AS cost FROM pgr_tsp('SELECT CAST(id AS INTEGER),ST_X(the_geom) AS x,ST_Y(the_geom) AS y FROM roads_vertices_pgr WHERE id IN (",paste(toString(unique(c(start_idx,pts,end_idx))),sep=','),")ORDER by id',",toString(start_idx),",",toString(end_idx),");",sep=''))
  #create route for each set of points using Djikstra algorithm
  for (i in seq(1,length(bird_tsp$id2),2)){
    route <- dbGetQuery(con,paste("SELECT seq,id2,cost FROM pgr_djikstra('SELECT id, source, target, cost ,reverse_cost FROM roads'",bird_tsp$id2[i],bird_tsp$id2[i+1],"true,true)",sep=',')) 
  }
  
  route_length <- sum(route$cost)*111
  x <- x+1
}

#write to db
#get geometry strings
geometries <- dbGetQuery(con,paste('SELECT id,ST_AsEWKT(the_geom) FROM vector.',city,'_streets_vertices_pgr WHERE id IN(',paste(toString(old_route$id2),sep=','),');',sep=''))
#returns sorted --> sort other as well
sorting_order <- order(old_route$id2)
seq <- old_route$seq[sorting_order]

#create string like "(seq_a,geom_a),(seq_b,geom_b),..."
mystr <- ''
for (i in 1:length(seq)){
  mystr <- paste(mystr,'(',paste(toString(seq[i]),paste("st_geomfromtext('",geometries$st_asewkt[i],"')",sep=''),sep=','),'),',sep='')
}
#remove last comma
mystr <- substr(mystr,1,nchar(mystr)-1)


###not working...
##write route to db
route_db <- dbGetQuery(con,paste("INSERT INTO ",city,"_route(seq,geom) VALUES ",mystr,";",sep=''))
#use string directly in sql:
write_it <- paste("INSERT INTO ",city,"_route(seq,geom) VALUES ",mystr,";",sep='')


