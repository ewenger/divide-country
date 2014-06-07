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

def readOsmFile(fileName):
    """
    Чтение данных из файла формата OSM XML. Ленивый вариант. Жрет память.
    """
    logger.info("reading file " + fileName)
    fl = open(fileName)
    root = etree.parse(fl)
    fl.close()
    result={'nodes':dict(), 'ways':dict(), 'rels':dict()}
    for rel in root.iter("relation"):
        rel_id = rel.get("id")
        result["rels"][rel_id] = [] 
        for member in rel.iter("member"):
            mem_type = member.get("type")
            mem_role = member.get("role")
            mem_id = member.get("ref")
#            logger.debug("rel {0} mem {1} type {2} role {3}".format(rel_id,mem_id,mem_type,mem_role))
            if ( mem_type == "way" and mem_role == "outer" ):
#                logger.debug("relation " + rel_id + ", appending member " + mem_id)
                result["rels"][rel_id].append(mem_id) 
    logger.info("found {0} relations".format( len(result['rels']) ))
    for way in root.iter("way"):
        way_id = way.get("id")
        result["ways"][way_id] = [] 
        for nd in way.iter("nd"):
            result["ways"][way_id].append( nd.get("ref") );
    logger.info("found {0} ways".format( len(result['ways']) ))
    for node in root.iter("node"):
        node_id = node.get("id")
        result["nodes"][node_id] = [ node.get("lat"), node.get("lon") ] 
    logger.info("found {0} nodes".format( len(result['nodes']) ))
    del root 
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
logger.info("finish")

