#! /usr/bin/python3

# Утилита для разделения страны на части, близкие по площади. Части 
# состоят из целого числа регионов

# $Id$

from lxml import etree
import logging

def readOsmFile(fileName):
    logger.debug("function readOsmFile")
    fl = open(fileName)
    root = etree.parse(fl)
    fl.close
    for element in root.iter("relation"):
        print(element.get("id"))

logging.basicConfig(level=logging.DEBUG,format="%(asctime)s %(levelname)s %(message)s")
logger=logging.getLogger(__name__)

readOsmFile("bound.osm")

