#! /usr/bin/python3

# Утилита для разделения набора областей на две связные части, близкие по площади. 
# Области, для который не получается определить соседей, попадают в 3ю часть:
# "islands"
#
# На входе: OSM файл, содержащий отношения областей и входящие в них
# точки и линии
# На выходе: три списка идентификаторов отношений

# $Id$

from lxml import etree
import logging
import argparse
from collections import deque, defaultdict, OrderedDict
from geographiclib.geodesic import Geodesic

osm = None
shapes = OrderedDict() 
shapes_areas = dict()
nested_shapes = dict()

class BadRingException(Exception):
    """
    Ошибка объединения линии в кольцо
    """

    def __init__(self, message):
        self.message = message

class OsmTarget:
    """
    XML handler
    """
    __countNodes=0;
    __countWays=0;
    __countRels=0;
    __finished=False;
    __good_relation=False;
    def __init__(self, result):
        self.__result = result
        self.__result["nodes"] = dict()
        self.__result["ways"] = dict()
        self.__result["rels"] = { "outer": dict(), "inner": dict() }
    def start(self, tag, attrib):
        if (tag=="node"): 
            self.__countNodes += 1;
            self.__result["nodes"][attrib["id"]] = [ attrib["lat"], attrib["lon"] ]
        elif (tag=="nd"):
            self.__result["ways"][self.__wayid].append(attrib["ref"])
        elif (tag=="way"):
            self.__countWays += 1;
            self.__wayid = attrib["id"]
            self.__result["ways"][self.__wayid] = [ ]
        elif (tag=="member" and self.__good_relation ):
            memtype=attrib["type"];
            ref=attrib["ref"];
            role=attrib["role"];
            if (memtype=="way" and role == "outer"):
                self.__result["rels"]["outer"][self.__relid].append(ref)
            if (memtype=="way" and role == "inner"):
                self.__result["rels"]["inner"][self.__relid].append(ref)
        elif (tag=="relation"):
            if ( attrib.get("action") == "delete" ):
                self.__good_relation = False
                return
            self.__good_relation = True
            self.__countRels += 1;
            self.__relid=attrib["id"];
            self.__result["rels"]["outer"][self.__relid] = [ ]
            self.__result["rels"]["inner"][self.__relid] = [ ]
        elif (tag=="osm"): 
            logger.info("parsing XML");
#    def end(self, tag):
#        return;
#    def data(self, data):
#        return
#    def comment(self, text):
#        return
    def close(self):
        logger.info("rels: {0}, ways: {1}, nodes: {2}".format(self.__countRels,self.__countWays,self.__countNodes))
        logger.info("end of the XML")
        return "closed!"

def readOsmFile(filename):
    """
    Чтение данных из файла формата OSM XML
    """
    result=dict()
    osmTarget=OsmTarget(result);
    parser=etree.XMLParser(target=osmTarget);
    f=open(filename,"r");
    etree.parse(f,parser);
    f.close();
    return result

def mergeWays(ways_to_merge):
    """
    объединяет линии в кольцо, или же выдает исключение, если это невозможно
    кольцо должно быть без самопересечений
    если колец несколько, берется наибольшее по площади

    ways_to_merge - id линий, которые объединяем
    выход - ( <список точек, входящих в кольцо>, <площадь в кв. метрах> )
    """
    ways=osm["ways"]
    ends = defaultdict(list)
    firstnode = None
    for way_id in ways_to_merge:
        for node_id in [ ways[way_id][0], ways[way_id][-1] ] :
            if (firstnode == None):
                firstnode = node_id
            ends[node_id].append(way_id)
    w = None
    rings = []
    ring = []
    n = firstnode
    node_count = 0
    while ( len(ends) > 0 ):
        if ( len(ends[n]) > 2 or (len(ends[n]) == 1 and w != ends[n][0]) ):
            raise BadRingException("Can't merge ways into ring (selfintersections?)")
        if ( len(ends[n]) == 1 ):
            #ring is closed, start new one (if possible)
            w = None
            del ends[n]
            rings.append(ring)
            ring = []
            if ( len(ends) > 0 ):
                n = list(ends.keys())[0]
                logger.warning("using only biggest ring")
            continue
        if ( w == ends[n][0] ):
            w = ends[n][1]
            del ends[n]
        elif ( w == ends[n][1] ):
            w = ends[n][0]
            del ends[n]
        elif ( w == None ):
            w = ends[n].pop()
        else:
            raise BadRingException("Can't merge ways into ring (something went wrong)")
        way = ways[w][:]
        if ( way[0] != n ):
            way.reverse()
        ring += way[1:]
        n = way[-1]
    maxarea = 0
    biggestring = None
    for ring in rings:
        area = calcShapeArea(ring)
        if area > maxarea:
            maxarea = area
            biggestring = ring
        logger.debug("area: {:15.2f} points: {:5}".format(area,len(ring)))
    return (biggestring, maxarea)

def geopoint(lat,lon): 
    """
    возвращает пару координат в виде dictionary {lat,lon}
    """
    return {'lat': lat, 'lon': lon}

def calcShapeArea(shape):
    """
    расчет площади выпуклого геомногоугольника
    """
    poly = [ geopoint( float(osm["nodes"][i][0]), float(osm["nodes"][i][1]) )  for i in shape ]
    area = abs(Geodesic.WGS84.Area(poly)["area"])
    return area

def createGraph(shapesids):
    """
    создание графа соседних областей
    узел - область
    ребро - к соседней области
    области считаются соседними, если имеют 2 или более общих точки
    """
    pointinshape = defaultdict(list)
    for s in shapesids:
        for p in shapes[s]:
            pointinshape[p].append(s)
    sharepoints = defaultdict(dict)
    for p in pointinshape:
        for i in range(0,len(pointinshape[p])-1):
            for j in range(i+1,len(pointinshape[p])):
                s1 = min(pointinshape[p][i], pointinshape[p][j])
                s2 = max(pointinshape[p][i], pointinshape[p][j])
                sharepoints[s1][s2] = sharepoints[s1].setdefault(s2,0) + 1;
    G = OrderedDict()
    for s1 in sorted(sharepoints.keys()):
        for s2 in sorted(sharepoints[s1].keys()):
            if ( sharepoints[s1][s2] > 1 ):
                if not s1 in G:
                    G[s1] = []
                if not s2 in G:
                    G[s2] = []
                G[s1].append(s2)
                G[s2].append(s1)
    return G

def getFarthestPoint(G,pointid):
    """
    поиск точки наиболее удаленной от точки point
    в графе G
    """
    startpoint = pointid
    bfs = dict()
    bfs[startpoint] = 1
    Q = deque()
    Q.append(startpoint)
    lastpoint = startpoint
    while ( len(Q) > 0 ):
        p = Q.popleft()
        for n in G[p]:
            if not n in bfs:
                bfs[n] = 1
                Q.append(n)
        lastpoint = p
    return lastpoint

def bfsMarkParts(G,bfs,startpoints):
    """
    маркирует части графа
    """
    Q = [ deque(), deque() ]
    area = [0,0]
    for p in range(0,2):
        Q[p].append(startpoints[p])
        area[p] = shapes_areas[startpoints[p]]
    while( len(Q[0]) > 0 or len(Q[1]) > 0 ):
        part_id =  1 
        if ( ( area[0] < area[1] and len(Q[0]) > 0 ) 
                or len(Q[1]) == 0  ):
            part_id = 0
        apart_id = abs(part_id - 1)
        p = Q[part_id].popleft()
        part_id = bfs[p]
        logger.debug("part {} p {} areapart {}".format(part_id,p,area[part_id]))
        for n in G[p]:
            if ( n in bfs ): 
                continue
            bfs[n] = part_id
            area[part_id] += shapes_areas[n]
            Q[part_id].append(n)
            logger.debug("part {} n {} arean {}".format(part_id,n,shapes_areas[n]))
            if (area[part_id] > area[apart_id] and len(Q[apart_id]) > 0):
                Q[part_id].appendleft(p) #put the same place we've taken it from
                break
    logger.debug("areas: {}".format(area))
    return

def divideGraph(G,p1,p2):
    """
    делит граф G на две примерно равные по площади связные части
    построение частей начинается с точек p1 и p2
    возвращает массив списков из идентификаторов полученных частей
    """
    bfs = {p1:0, p2:1}
    bfsMarkParts(G,bfs,[p1,p2])
    result = [[],[]]
    for s in bfs:
        result[bfs[s]].append(s)
    return [ sorted(result[0]), sorted(result[1]) ]

def getNestedShapes():
    """
    поиск вложенных областей
    result[s] - список областей, внутри которых есть кусочек области s
    """
    pointinshape = {
        "outer": defaultdict(set),
        "inner": defaultdict(set)
    }
    
    for t in ["outer","inner"]:
        for r in osm["rels"][t]:
            for w in osm["rels"][t][r]:
                for n in osm["ways"][w]:
                    pointinshape[t][n].add(r)
    point_set = set(pointinshape["outer"].keys()) & set (pointinshape["inner"].keys())
    sharepoints = defaultdict(dict)
    for p in point_set:
        for i in pointinshape["inner"][p]:
            for o in pointinshape["outer"][p]:
                sharepoints[i][o] = sharepoints[i].setdefault(o,0) + 1;
    result = defaultdict(list)
    for si in sharepoints:
        for so in sharepoints[si]:
            if sharepoints[si][so] >= 2:
                result[so].append(si)  # outer way belongs to the inner shape
    return result

#======================================================================================

logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

logger.info("start")
logger.info("parse arguments")
parser = argparse.ArgumentParser(description="Divide group of OSM multipolygons into two complete parts")
parser.add_argument("--file","-f",required=True,
        help="input OSM file (required)")
parser.add_argument("--num","-n",type=int, default=1,
        help="repeat n times (you will get 2^n parts, default: 1)")
parser.add_argument("--debug","-d", action="store_true", default=False, 
        help="show debug messages (default: off)")
args = parser.parse_args();
if (args.debug):
    logger.setLevel(logging.DEBUG)

logger.info("read OSM file")
osm = readOsmFile(args.file)
logger.info("merge ways into rings and calc area")
for k in osm["rels"]["outer"]:
    logger.debug(k)
    ( shapes[k], shapes_areas[k] )  = mergeWays(osm["rels"]["outer"][k])
    logger.debug("area {:10} {:10.2f} km2".format(k,shapes_areas[k]/1000000))

parts = [ list(shapes.keys()) ]
for loopnum in range(0,args.num):
    logger.debug("partition {}".format(loopnum))
    newparts = []
    for part in parts:
        if ( len(part) < 2 ):
            newparts.append(part)
            continue
        logger.info("create graph")
        logger.debug("number of shapes: {}".format(len(part)))
        G = createGraph(part)
        logger.debug("graph size: {}".format(len(G)))
        s1 = getFarthestPoint(G,list(G.keys())[0])
        s2 = getFarthestPoint(G,s1)
        logger.info("divide graph")
        newparts += divideGraph(G,s1,s2)
    parts = newparts

logger.info("get nested shapes")
nested_shapes = getNestedShapes()
islands = set(shapes.keys())
for part in parts:
    islands -= set(part)
for si in ( islands & set(nested_shapes.keys()) ):
    so = nested_shapes[si][0]
    for part in parts:
        if so in part:
            part.append(si)
    islands.remove(si)
parts.append([])
for s in islands:
    parts[-1].append(s)

logger.info("print result")
for p in range(0,len(parts)):
    if ( len(parts[p]) > 0 ):
        logger.debug("part {}: {}".format(p,len(parts[p])))
        print("{}: {}".format(p,", ".join(parts[p])))
if ( len(islands) > 0 ):
    logger.debug("islands: {}".format(p,len(islands)))
    print("islands: {}".format(", ".join(islands)))

logger.info("finish")

