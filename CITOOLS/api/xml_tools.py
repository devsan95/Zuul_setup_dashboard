#! /usr/bin/env python2.7
# -*- coding:utf8 -*-


import xml.etree.ElementTree as ET


class XmlParser(object):
    def __init__(self, xml):
        self.xml = xml
        if isinstance(xml, basestring):
            self.root = ET.fromstring(self.xml)
        else:
            self.tree = ET.parse(self.xml)
            self.root = self.tree.getroot()

    def is_element_exist(self, ele_name):
        for elem in self.root.iter():
            if elem.tag == ele_name:
                return True
        return False

    def get_root(self):
        return self.root

    # search operation
    def get_all_elements(self):
        root = self.root
        return [elem.tag for elem in root.iter()]

    def print_root_children(self):
        for child in self.root:
            print(child.tag, child.attrib, child.text)

    def get_element_details(self, element_name):
        if self.is_element_exist(element_name):
            ele_list = []
            for element in self.root.iter(element_name):
                tag = element.tag
                attrib = element.attrib
                text = element.text
                ele_list.append({"tag": tag, "attrib": attrib, "text": text})
            return ele_list
        else:
            raise Exception(
                "Not found a element named {}".format(element_name)
            )

    def get_element_by_tag(self, tag):
        for elem in self.root.iter():
            if elem.tag == tag:
                return elem
        return None

    # write or revise xml
    # only the input xml is a xml file path or object this can be
    # taken into effect
    def update(self):
        self.root.write(self.xml)

    def set_tag_text(self, tag, contents):
        if self.is_element_exist(tag):
            self.get_element_by_tag(tag).text = contents
            return self.root
        return None

    def set_tag_attrib(self, tag, attrib_name, value):
        self.root.find(tag).set(attrib_name, value)
        self.update()

    def add_element_of_tag(self, tag):
        pass

    def is_element(self, ele):
        return ET.iselement(ele)

    def element_to_string(self, ele):
        if self.is_element(ele):
            return ET.tostring(ele)
        print("{} is not a element object!".format(ele))
        return ele

    def root_to_string(self):
        return ET.tostring(self.root)
