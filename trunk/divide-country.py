#! /usr/bin/python3

# Утилита для разделения страны на части, близкие по площади. Части 
# состоят из целого числа регионов

# $Id$

from lxml import etree
import logging

def readOsmFile(fileName):
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
    return result

logging.basicConfig(level=logging.DEBUG,format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

logger.info("start")
osm = readOsmFile("bound.osm")
logger.info("finish")

