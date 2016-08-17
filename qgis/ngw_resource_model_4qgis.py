# -*- coding: utf-8 -*-
"""
/***************************************************************************
 Common Plugins settings

 NextGIS WEB API
                             -------------------
        begin                : 2014-10-31
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
import os
import glob
import shutil
import zipfile
import tempfile

from PyQt4.QtCore import *

from qgis.core import *
from qgis.gui import *

# from ..qt.qt_ngw_resource_model import *
# from ..qt.qt_ngw_resource_edit_model import *
# from ..qt.qt_ngw_resource_item import *
from ..qt.qt_ngw_resource_base_model import QNGWResourcesModelExeption
from ..qt.qt_ngw_resource_edit_model import QNGWResourcesModel
from ..qt.qt_ngw_resource_model_job import NGWResourceModelJob

from ..core.ngw_webmap import NGWWebMapLayer, NGWWebMapGroup, NGWWebMapRoot
from ..core.ngw_resource_creator import ResourceCreator

from ngw_plugin_settings import NgwPluginSettings


class QNGWResourcesModel4QGIS(QNGWResourcesModel):
    JOB_IMPORT_QGIS_RESOURCE = "IMPORT_QGIS_RESOURCE"
    JOB_IMPORT_QGIS_PROJECT = "IMPORT_QGIS_PROJECT"

    def __init__(self, parent):
        QNGWResourcesModel.__init__(self, parent)

    # def __del__(self):
    #     print "QNGWResourcesModel4QGIS __del__"
    #     QNGWResourcesModel.__del__(self)

    def createNGWLayer(self, qgs_map_layer, parent_index):
        if not parent_index.isValid():
            parent_index = self.index(0, 0, parent_index)

        parent_index = self._nearest_ngw_group_resource_parent(parent_index)

        parent_item = parent_index.internalPointer()
        ngw_parent_resource = parent_item.data(0, Qt.UserRole)

        worker = QGISResourceImporter(qgs_map_layer, ngw_parent_resource)
        self._stratJobOnNGWResource(
            parent_index,
            worker,
            self.JOB_IMPORT_QGIS_RESOURCE,
            [self.__importFinished],
        )

    def __importFinished(self):
        job_index = self._getJobIndexByJob(self.sender())
        if job_index == -1:
            return

        (index, job) = self.jobs.pop(
            job_index
        )

        self._reloadChildren(index)

    def tryImportCurentQGISProject(self, ngw_group_name, parent_index, iface):
        if not parent_index.isValid():
            parent_index = self.index(0, 0, parent_index)

        parent_index = self._nearest_ngw_group_resource_parent(parent_index)

        parent_item = parent_index.internalPointer()
        ngw_resource_parent = parent_item.data(0, parent_item.NGWResourceRole)

        worker = CurrentQGISProjectImporter(ngw_group_name, ngw_resource_parent, iface)
        self._stratJobOnNGWResource(
            parent_index,
            worker,
            self.JOB_IMPORT_QGIS_PROJECT,
            [self.__importFinished],
        )


class QGISResourceJob(NGWResourceModelJob):
    def __init__(self):
        NGWResourceModelJob.__init__(self)

        self.sanitize_fields_names = ["id", "type", "source"]

    def importQGISMapLayer(self, qgs_map_layer, ngw_parent_resource):
        ngw_parent_resource.update()

        layer_name = qgs_map_layer.name()
        chd_names = [ch.common.display_name for ch in ngw_parent_resource.get_children()]
        new_layer_name = self.generate_unique_name(layer_name, chd_names)

        layer_type = qgs_map_layer.type()
        if layer_type == qgs_map_layer.VectorLayer:
            return self.importQgsVectorLayer(qgs_map_layer, ngw_parent_resource, new_layer_name)

        elif layer_type == QgsMapLayer.RasterLayer:
            return self.importQgsRasterLayer(qgs_map_layer, ngw_parent_resource, new_layer_name)

        return None

    def importQgsRasterLayer(self, qgs_raster_layer, ngw_parent_resource, new_layer_name):
        def uploadFileCallback(total_size, readed_size):
            self.statusChanged.emit(
                "%s - Upload (%d %%)" % (
                    qgs_raster_layer.name(),
                    readed_size * 100 / total_size
                )
            )
        layer_provider = qgs_raster_layer.providerType()
        if layer_provider == 'gdal':
            filepath = qgs_raster_layer.source()
            ngw_raster_layer = ResourceCreator.create_raster_layer(
                ngw_parent_resource,
                filepath,
                new_layer_name,
                uploadFileCallback
            )

            return ngw_raster_layer

    def importQgsVectorLayer(self, qgs_vector_layer, ngw_parent_resource, new_layer_name):
        def uploadFileCallback(total_size, readed_size):
            self.statusChanged.emit(
                "%s - Upload (%d %%)" % (
                    qgs_vector_layer.name(),
                    readed_size * 100 / total_size
                )
            )

        if qgs_vector_layer.geometryType() in [QGis.NoGeometry, QGis.UnknownGeometry]:
            self.errorOccurred.emit(
                QNGWResourcesModelExeption(
                    "Vector layer '%s' has no geometry" % qgs_vector_layer.name()
                )
            )
            return None

        filepath = self.prepareImportFile(qgs_vector_layer)

        if filepath is None:
            self.errorOccurred.emit(
                QNGWResourcesModelExeption(
                    "Can't prepare layer'%s'. Skiped!" % qgs_vector_layer.name()
                )
            )
            return None

        ngw_vector_layer = ResourceCreator.create_vector_layer(
            ngw_parent_resource,
            filepath,
            new_layer_name,
            uploadFileCallback
        )

        self.statusChanged.emit(
            "%s - Finishing" % qgs_vector_layer.name()
        )

        os.remove(filepath)
        return ngw_vector_layer

    def prepareImportFile(self, qgs_vector_layer):
        self.statusChanged.emit(
            "%s - Prepare" % qgs_vector_layer.name()
        )

        layer_has_mixed_geoms = False
        layer_has_bad_fields = False
        if NgwPluginSettings.get_sanitize_fix_geometry():
            if self.hasSimpleAndMultyGeom(qgs_vector_layer):
                layer_has_mixed_geoms = True
        if NgwPluginSettings.get_sanitize_rename_fields():
            if self.hasBadFields(qgs_vector_layer):
                layer_has_bad_fields = True

        if layer_has_mixed_geoms or layer_has_bad_fields:
            layer = self.createLayer4Upload(qgs_vector_layer, layer_has_mixed_geoms, layer_has_bad_fields)
        else:
            layer = qgs_vector_layer

        # QgsMessageLog.logMessage("source: %s" % (layer.source(),))
        # QgsMessageLog.logMessage("fieldsCount: %d" % (len(layer.dataProvider().fields()),))
        # QgsMessageLog.logMessage("featureCount: %d" % (layer.featureCount(),))
        # QgsMessageLog.logMessage("geometryType: %d" % (layer.geometryType(),))
        # QgsMessageLog.logMessage("wkbType: %d" % (layer.wkbType(),))
        # for feature in layer.getFeatures():
        #     QgsMessageLog.logMessage("    feature wkbType: %d" % (feature.geometry().wkbType(),))

        import_format = u'ESRI Shapefile'
        if layer.featureCount() > 0:
            layer_provider = layer.dataProvider()
            if layer_provider.storageType() in [u'ESRI Shapefile']:
                import_format = layer_provider.storageType()
            else:
                import_format = u"GeoJSON"

        if import_format == u'ESRI Shapefile':
            return self.prepareAsShape(layer)
        else:
            return self.prepareAsJSON(layer)

    def hasSimpleAndMultyGeom(self, qgs_vector_layer):
        has_simple_geometries = False
        has_multipart_geometries = False

        features_count = qgs_vector_layer.featureCount()
        features_counter = 0
        for feature in qgs_vector_layer.getFeatures():
            self.statusChanged.emit(
                "%s - Check geometry (%d %%)" % (
                    qgs_vector_layer.name(),
                    features_counter * 100 / features_count
                )
            )
            features_counter += 1
            if feature.geometry().isMultipart():
                has_multipart_geometries = True
            else:
                has_simple_geometries = True

            if has_multipart_geometries and has_simple_geometries:
                break

        self.statusChanged.emit(
            "%s - Check geometry (%d %%)" % (
                qgs_vector_layer.name(),
                100
            )
        )
        return has_multipart_geometries and has_simple_geometries

    def hasBadFields(self, qgs_vector_layer):
        exist_fields_names = [field.name() for field in qgs_vector_layer.fields()]
        common_fields = list(set(exist_fields_names).intersection(self.sanitize_fields_names))

        return len(common_fields) > 0

    def createLayer4Upload(self, qgs_vector_layer_src, has_mixed_geoms, has_bad_fields):
        # QgsMessageLog.logMessage("createLayer4Upload")

        geometry_type = self.determineGeometry4MemoryLayer(qgs_vector_layer_src, has_mixed_geoms)

        field_name_map = {}
        if has_bad_fields:
            field_name_map = self.getFieldsForRename(qgs_vector_layer_src)

            if len(field_name_map) != 0:
                self.warningOccurred.emit(
                    QCoreApplication.translate(
                        "QGISResourceJob",
                        "We've renamed fields {0} for layer '{1}'. Style for this layer may become invalid."
                    ).format(
                        field_name_map.keys(),
                        qgs_vector_layer_src.name()
                    )
                )

        qgs_vector_layer_dst = QgsVectorLayer(
            "%s?crs=epsg:4326" % geometry_type,
            "temp",
            "memory"
        )

        qgs_vector_layer_dst.startEditing()

        for field in qgs_vector_layer_src.fields():
            field.setName(
                field_name_map.get(field.name(), field.name())
            )
            qgs_vector_layer_dst.addAttribute(field)

        qgs_vector_layer_dst.commitChanges()
        qgs_vector_layer_dst.startEditing()
        features_count = qgs_vector_layer_src.featureCount()
        features_counter = 1
        for feature in qgs_vector_layer_src.getFeatures():
            if has_mixed_geoms:
                new_geometry = feature.geometry()
                new_geometry.convertToMultiType()
                feature.setGeometry(
                    new_geometry
                )
            qgs_vector_layer_dst.addFeature(feature)

            self.statusChanged.emit(
                "%s - Prepare layer for import (%d %%)" % (
                    qgs_vector_layer_src.name(),
                    features_counter * 100 / features_count
                )
            )
            features_counter += 1

        qgs_vector_layer_dst.commitChanges()

        return qgs_vector_layer_dst

    def determineGeometry4MemoryLayer(self, qgs_vector_layer, has_mixed_geoms):
        geometry_type = None
        if qgs_vector_layer.geometryType() == QGis.Point:
            geometry_type = "point"
        elif qgs_vector_layer.geometryType() == QGis.Line:
            geometry_type = "linestring"
        elif qgs_vector_layer.geometryType() == QGis.Polygon:
            geometry_type = "polygon"

        # if has_multipart_geometries:
        if has_mixed_geoms:
            geometry_type = "multi" + geometry_type

        return geometry_type

    def getFieldsForRename(self, qgs_vector_layer):
        field_name_map = {}

        exist_fields_names = [field.name() for field in qgs_vector_layer.fields()]
        for field in qgs_vector_layer.fields():
            if field.name() in self.sanitize_fields_names:
                new_field_name = field.name()
                suffix = 1
                while new_field_name in exist_fields_names:
                    new_field_name = field.name() + str(suffix)
                    suffix += 1
                field_name_map.update({field.name(): new_field_name})

        return field_name_map

    def prepareAsShape(self, qgs_vector_layer):
        # QgsMessageLog.logMessage("prepareAsShape")

        tmp_dir = tempfile.mkdtemp('ngw_api_prepare_import')
        tmp_shp = os.path.join(tmp_dir, '4import.shp')

        import_crs = QgsCoordinateReferenceSystem(4326, QgsCoordinateReferenceSystem.EpsgCrsId)
        QgsVectorFileWriter.writeAsVectorFormat(
            qgs_vector_layer,
            tmp_shp,
            'utf-8',
            import_crs,
        )

        tmp = tempfile.mktemp('.zip')
        basePath = os.path.splitext(tmp_shp)[0]
        baseName = os.path.splitext(os.path.basename(tmp_shp))[0]

        self.statusChanged.emit(
            "%s - Packing" % qgs_vector_layer.name()
        )

        zf = zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED)
        for i in glob.iglob(basePath + '.*'):
            ext = os.path.splitext(i)[1]
            zf.write(i, baseName + ext)

        zf.close()
        shutil.rmtree(tmp_dir)

        return tmp

    def prepareAsJSON(self, qgs_vector_layer):
        # QgsMessageLog.logMessage("prepareAsJSON")

        tmp = tempfile.mktemp('.geojson')
        import_crs = QgsCoordinateReferenceSystem(4326, QgsCoordinateReferenceSystem.EpsgCrsId)
        QgsVectorFileWriter.writeAsVectorFormat(
            qgs_vector_layer,
            tmp,
            'utf-8',
            import_crs,
            'GeoJSON'
        )

        return tmp

    def addStyle(self, qgs_map_layer, ngw_layer_resource):
        def uploadFileCallback(total_size, readed_size):
            self.statusChanged.emit(
                "Style for %s - Upload (%d %%)" % (
                    qgs_map_layer.name(),
                    readed_size * 100 / total_size
                )
            )

        self.statusChanged.emit(
            "Style for %s - Save as qml" % qgs_map_layer.name()
        )
        layer_type = qgs_map_layer.type()
        if layer_type == QgsMapLayer.VectorLayer:
            tmp = tempfile.mktemp('.qml')
            msg, saved = qgs_map_layer.saveNamedStyle(tmp)

            ngw_resource = ResourceCreator.create_vector_layer_style(
                ngw_layer_resource,
                tmp,
                qgs_map_layer.name(),
                uploadFileCallback
            )

            os.remove(tmp)
            return ngw_resource
        elif layer_type == QgsMapLayer.RasterLayer:
            layer_provider = qgs_map_layer.providerType()
            if layer_provider == 'gdal':
                ngw_resource = ResourceCreator.create_raster_layer_style(
                    ngw_layer_resource,
                    qgs_map_layer.name()
                )
                return ngw_resource

        return None


class QGISResourceImporter(QGISResourceJob):
    def __init__(self, qgs_map_layer, ngw_parent_resource):
        QGISResourceJob.__init__(self)
        self.qgs_map_layer = qgs_map_layer
        self.ngw_parent_resource = ngw_parent_resource

    def _do(self):
        try:
            ngw_resource = self.importQGISMapLayer(
                self.qgs_map_layer,
                self.ngw_parent_resource
            )

            if ngw_resource is None:
                return

            self.addStyle(
                self.qgs_map_layer,
                ngw_resource
            )

            self.dataReceived.emit(ngw_resource)

        except Exception as e:
            self.errorOccurred.emit(e)


class CurrentQGISProjectImporter(QGISResourceJob):
    def __init__(self, new_group_name, ngw_resource_parent, iface):
        QGISResourceJob.__init__(self)
        self.new_group_name = new_group_name
        self.ngw_resource_parent = ngw_resource_parent
        self.iface = iface

    def _do(self):
        current_project = QgsProject.instance()

        try:
            chd_names = [ch.common.display_name for ch in self.ngw_resource_parent.get_children()]

            new_group_name = self.generate_unique_name(self.new_group_name, chd_names)

            ngw_group_resource = ResourceCreator.create_group(
                self.ngw_resource_parent,
                new_group_name
            )

            ngw_webmap_root_group = NGWWebMapRoot()

            def process_one_level_of_layers_tree(qgsLayerTreeItems, ngw_resource_group, ngw_webmap_item):
                for qgsLayerTreeItem in qgsLayerTreeItems:

                    if isinstance(qgsLayerTreeItem, QgsLayerTreeLayer):
                        ngw_layer_resource = self.importQGISMapLayer(
                            qgsLayerTreeItem.layer(),
                            ngw_resource_group
                        )

                        if ngw_layer_resource is None:
                            continue

                        ngw_style_resource = self.addStyle(
                            qgsLayerTreeItem.layer(),
                            ngw_layer_resource
                        )

                        if ngw_style_resource is None:
                            continue

                        ngw_webmap_item.appendChild(
                            NGWWebMapLayer(
                                ngw_style_resource.common.id,
                                qgsLayerTreeItem.layer().name(),
                                qgsLayerTreeItem.isVisible() == Qt.Checked
                            )
                        )

                    if isinstance(qgsLayerTreeItem, QgsLayerTreeGroup):
                        chd_names = [ch.common.display_name for ch in ngw_resource_group.get_children()]

                        group_name = qgsLayerTreeItem.name()
                        self.statusChanged.emit("Import folder %s" % group_name)

                        if group_name in chd_names:
                            id = 1
                            while(group_name + str(id) in chd_names):
                                id += 1
                            group_name += str(id)

                        ngw_resource_child_group = ResourceCreator.create_group(
                            ngw_resource_group,
                            group_name
                        )

                        ngw_webmap_child_group = NGWWebMapGroup(
                            group_name,
                            qgsLayerTreeItem.isExpanded()
                        )
                        ngw_webmap_item.appendChild(
                            ngw_webmap_child_group
                        )

                        process_one_level_of_layers_tree(
                            qgsLayerTreeItem.children(),
                            ngw_resource_child_group,
                            ngw_webmap_child_group
                        )

            process_one_level_of_layers_tree(
                current_project.layerTreeRoot().children(),
                ngw_group_resource,
                ngw_webmap_root_group
            )

            self.statusChanged.emit("Import curent qgis project: create webmap")
            self.add_webmap(
                ngw_group_resource,
                self.new_group_name + u"-webmap",
                ngw_webmap_root_group.children
            )
        except Exception as e:
            self.errorOccurred.emit(e)

    def add_webmap(self, ngw_resource, ngw_webmap_name, ngw_webmap_items):
        rectangle = self.iface.mapCanvas().extent()
        ct = QgsCoordinateTransform(
            self.iface.mapCanvas().mapSettings().destinationCrs(),
            QgsCoordinateReferenceSystem(4326, QgsCoordinateReferenceSystem.EpsgCrsId)
        )

        bbox = ct.transform(QgsRectangle(-179.9, -89.9, 179.9, 89.9), QgsCoordinateTransform.ReverseTransform)
        rectangle = rectangle.intersect(bbox)

        rectangle = ct.transform(rectangle)

        ngw_webmap_items_as_dicts = [item.toDict() for item in ngw_webmap_items]
        ngw_resource = ResourceCreator.create_webmap(
            ngw_resource,
            ngw_webmap_name,
            ngw_webmap_items_as_dicts,
            [
                rectangle.xMinimum(),
                rectangle.xMaximum(),
                rectangle.yMaximum(),
                rectangle.yMinimum(),
            ]
        )

        return ngw_resource
