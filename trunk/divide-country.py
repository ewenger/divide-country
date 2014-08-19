#! /usr/bin/python3

# Утилита для разделения страны на части, близкие по площади. Части 
# состоят из целого числа регионов

# $Id$

from lxml import etree
import logging
from collections import deque, defaultdict, OrderedDict
from geographiclib.geodesic import Geodesic

osm = None
shapes = OrderedDict() 
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
    def __init__(self, result):
        self.__result = result
        self.__result["nodes"] = dict()
        self.__result["ways"] = dict()
        self.__result["rels"] = dict()
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
        elif (tag=="member" ):
            memtype=attrib["type"];
            ref=attrib["ref"];
            role=attrib["role"];
            if (memtype=="way" and role == "outer"):
                self.__result["rels"][self.__relid].append(ref)
        elif (tag=="relation"):
            self.__countRels += 1;
            self.__relid=attrib["id"];
            self.__result["rels"][self.__relid] = [ ]
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
    если колец несколько, используется только первое

    ways_to_merge - id линий, которые объединяем
    выход - список точек, входящих в кольцо
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
    ring = []
    n = firstnode
    node_count = 0
    while ( len(ring) == 0 or n != firstnode ):
        if ( len(ends[n]) != 2 ):
            raise BadRingException("Can't merge ways into ring (selfintersections?)")
        if ( w != ends[n][0] ):
            w = ends[n][0]
        else :
            w = ends[n][1]
        way = ways[w][:]
        if ( way[0] != n ):
            way.reverse()
        ring += way[1:]
        node_count += 1
        n = way[-1]
    if ( node_count != len(ends) ):
        logger.warning("using only first outer ring")
    return ring

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
logger.info("merge ways into rings")
for k in osm["rels"]:
    shapes[k] = mergeWays(osm["rels"][k])
logger.info("calculate areas")
for s in shapes:
    shapes_areas[s] = calcShapeArea(shapes[s])
    logger.debug("area {:10} {:10.2f} km2".format(s,shapes_areas[s]/1000000))
logger.info("create graph")
G = createGraph(shapes.keys())
s1 = getFarthestPoint(G,list(G.keys())[0])
s2 = getFarthestPoint(G,s1)

logger.info("divide graph")
parts = divideGraph(G,s1,s2)

logger.info("print result")
for p in range(0,2):
    print("{}: ".format(p),end="")
    for s in range(0,len(parts[p])):
        print(parts[p][s],end="")
        if ( s < len(parts[p]) - 1):
            print(", ",end="")
        else:
            print("")

logger.info("finish")

