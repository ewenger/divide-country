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
from collections import deque, defaultdict, OrderedDict
from geographiclib.geodesic import Geodesic

osm = None
shapes = OrderedDict() 
shapes_inner = OrderedDict() 
shapes_areas = dict()

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

def mergeWays(ways_to_merge,return_list=False):
    """
    объединяет линии в кольцо, или же выдает исключение, если это невозможно
    кольцо должно быть без самопересечений

    ways_to_merge - id линий, которые объединяем
    return_list - вернуть список всех колец (иначе самое большое)
    выход - ( <список точек, входящих в кольцо>, <площадь в кв. метрах> )
            либо список колец (см return_list)
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
                if (not return_list):
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
    if return_list:
        return rings
    maxarea = 0
    biggestring = None
    for ring in rings:
        area = calcShapeArea(ring)
        if area > maxarea:
            maxarea = area
            biggestring = ring
    return (biggestring, area)

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
    pointinshape_inner = defaultdict(list)
    for s in shapesids:
        for p in shapes[s]:
            pointinshape[p].append(s)
            pointinshape_inner[p].append(s)
        for plist in shapes_inner[s]:
            for p in plist:
                pointinshape_inner[p].append(s)
    sharepoints = defaultdict(dict)
    for p in pointinshape:
        for i in range(0,len(pointinshape[p])-1):
            for j in range(i+1,len(pointinshape[p])):
                s1 = min(pointinshape[p][i], pointinshape[p][j])
                s2 = max(pointinshape[p][i], pointinshape[p][j])
                sharepoints[s1][s2] = sharepoints[s1].setdefault(s2,0) + 1;
    sharepoints_inner = defaultdict(dict)
    for p in pointinshape_inner:
        for i in range(0,len(pointinshape_inner[p])-1):
            for j in range(i+1,len(pointinshape_inner[p])):
                s1 = min(pointinshape_inner[p][i], pointinshape_inner[p][j])
                s2 = max(pointinshape_inner[p][i], pointinshape_inner[p][j])
                sharepoints_inner[s1][s2] = sharepoints_inner[s1].setdefault(s2,0) + 1;
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
    islands = set(shapesids) - set(G.keys())
    for s1 in sorted(sharepoints_inner.keys()):
        for s2 in sorted(sharepoints_inner[s1].keys()):
            if ( s1 in islands or s2 in islands):
                if ( sharepoints_inner[s1][s2] > 1 ):
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

def bfsMarkParts(G,bfs,startpoints,part_id):
    """
    маркирует части графа
    """
    p = startpoints[part_id]
    Q = deque()
    Q.append(p)
    area = shapes_areas[p]
    total_area = sum(shapes_areas.values())
    next_part_marked = False
    while( len(Q) > 0 ):
        p = Q.popleft()
        for n in G[p]:
            if ( n in bfs ): 
                continue
            if ( ( part_id < len(startpoints) - 1 ) and 
                    ( not next_part_marked ) and
                    ( area >= total_area/2 ) ):
                bfsMarkParts(G,bfs,startpoints,part_id+1)
                next_part_marked = True
            if ( n in bfs ): 
                continue
            bfs[n] = part_id
            area += shapes_areas[n]
            Q.append(n)
    return

def divideGraph(G,p1,p2):
    """
    делит граф G на две примерно равные по площади связные части
    построение частей начинается с точек p1 и p2
    возвращает массив списков из идентификаторов полученных частей
    """
    bfs = {p1:0, p2:1}
    bfsMarkParts(G,bfs,[p1,p2],0)
    result = [[],[]]
    for s in bfs:
        result[bfs[s]].append(s)
    return [ sorted(result[0]), sorted(result[1]) ]

#======================================================================================

logging.basicConfig(level=logging.DEBUG,format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

logger.info("start")
logger.info("read OSM file")
osm = readOsmFile("test/test2.osm")
logger.info("merge ways into rings and calc area")
for k in osm["rels"]["outer"]:
    ( shapes[k], shapes_areas[k] )  = mergeWays(osm["rels"]["outer"][k])
    shapes_inner[k] = mergeWays(osm["rels"]["inner"][k],True)
    logger.debug("area {:10} {:10.2f} km2".format(k,shapes_areas[k]/1000000))
logger.info("create graph")
G = createGraph(shapes.keys())
logger.debug("graph size: {}".format(len(G)))
s1 = getFarthestPoint(G,list(G.keys())[0])
s2 = getFarthestPoint(G,s1)

logger.info("divide graph")
parts = divideGraph(G,s1,s2)
parts.append([])
for s in shapes:
    if (not s in G):
        parts[2].append(s)    

logger.debug("part 0: {}".format(len(parts[0])))
logger.debug("part 1: {}".format(len(parts[1])))
logger.debug("part islands: {}".format(len(parts[2])))
logger.info("print result")
partnames = ["part1", "part2", "islands"]
for p in range(0,3):
    print("{}: ".format(partnames[p]),end="")
    for s in range(0,len(parts[p])):
        print(parts[p][s],end="")
        if ( s < len(parts[p]) - 1):
            print(", ",end="")
        else:
            print("")

logger.info("finish")

