# -*- coding: utf-8 -*-
"""
/***************************************************************************
    NextGIS WEB API
                              -------------------
        begin                : 2014-11-19
        git sha              : $Format:%H$
        copyright            : (C) 2014 by NextGIS
        email                : info@nextgis.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
from os import path
import urllib.parse

from .ngw_resource import NGWResource, DICT_TO_OBJ, LIST_DICT_TO_LIST_OBJ

from ..utils import ICONS_DIR, log


class NGWWfsService(NGWResource):

    type_id = 'wfsserver_service'
    icon_path = path.join(ICONS_DIR, 'wfs.svg')
    type_title = 'NGW WFS Service'

    def __init__(self, resource_factory, resource_json):
        NGWResource.__init__(self, resource_factory, resource_json)

    def _construct(self):
        NGWResource._construct(self)
        #wfsserver_service
        self.wfs = DICT_TO_OBJ(self._json[self.type_id])
        if hasattr(self.wfs, "layers"):
            self.wfs.layers = LIST_DICT_TO_LIST_OBJ(self.wfs.layers)

    def get_wfs_url(self, layer_keyname):
        creds = self._res_factory.connection.get_auth()
        return '%s%s%s' % (
            self.get_absolute_api_url(),
            '/wfs?SERVICE=WFS&TYPENAME=%s' % layer_keyname,
            #'&username=%s&password=%s' % (creds[0], creds[1])
            '&username=%s&password=%s' % (urllib.parse.quote_plus(creds[0]), urllib.parse.quote_plus(creds[1]))
        )

    def get_layers(self):
        return self._json["wfsserver_service"]["layers"]

    def get_source_layer(self, layer_id):
        return self._res_factory.get_resource(layer_id)