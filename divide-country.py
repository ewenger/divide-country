#! /usr/bin/python3

# Утилита для разделения страны на части, близкие по площади. Части 
# состоят из целого числа регионов

# $Id$

from lxml import etree
import logging

class BadRingException(Exception):
    """
    Ошибка объединениня линии в кольцо
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

def mergeWays(ways_to_merge, ways):
    """
    объединяет линии в кольцо, или же выдает исключение, если это невозможно
    кольцо должно быть без самопересечений
    если колец несколько, используется только первое

    ways_to_merge - id линий, которые объединяем
    ways - массивы точек, определяющих линии
    выход - список точек, входящих в кольцо
    """
    ends = dict()
    firstnode = None
    for way_id in ways_to_merge:
        for node_id in [ ways[way_id][0], ways[way_id][-1] ] :
            if (firstnode == None):
                firstnode = node_id
            if ( not node_id in ends ):
                ends[node_id] = []
            ends[node_id].append(way_id)
    w = None
    ring = []
    n = firstnode
    node_count = 0
    while ( len(ring) == 0 or ring[0] != n ):
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

logging.basicConfig(level=logging.DEBUG,format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

logger.info("start")
osm = readOsmFile("bound.osm")
print(osm["rels"])
logger.info("finish")


