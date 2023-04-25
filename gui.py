#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Feb 23 11:08:59 2023

@author: ricardoc
Kubernetes Management Tool
"""

import sys
from PyQt6.QtCore import Qt, QAbstractTableModel
from PyQt6.QtWidgets import (
    QApplication, 
    QWidget, 
    QFileDialog, 
    QGridLayout,
    QPushButton, 
    QLabel,
    QListWidget,
    QTableView
)
from pathlib import Path
import pandas as pd
from kubernetes import client, config

class Kube:
    def __init__(self, path):
        self.path = path
        #load kube config file to gain access to kubernetes api clients
        config.load_kube_config(config_file=self.path)
        #loading necessary api clients
        self.core_api = client.CoreV1Api()
        self.app_api = client.AppsV1Api()
        
    def getDeployments(self):
        #grab list of deployments
        deps = self.app_api.list_namespaced_deployment(namespace='application').items
        #grab list of services
        services = self.core_api.list_namespaced_service('application').items
        #this list will be returned
        deployment_list = []
        for dep in deps:
            cm_list = []
            ports = ''
            port_dict = {'app_protocol': [], 'name': [], 'node_port': [], 'port': [], 'protocol': [], 'target_port': []}
            #only need container spec for this function
            container = dep.spec.template.spec.containers[0]
            #loop through services and grab the service that matches container
            for service in services:
                if container.name in service.metadata.name:
                    ports = service.spec.ports
                    for port in ports:
                        current_port = port.to_dict()
                        for key, value in current_port.items():
                            port_dict[key].append(value)
                        
                    
            #this will get replica status, that shows what containers are running
            try:
                status = dep.status
                if status.replicas == None:
                    replica = 0 
                else: 
                    replica = status.replicas
                if status.available_replicas == None:
                    available = 0 
                else: 
                    available = status.available_replicas
                replica_status = "{}/{}".format(available, replica)
            except:
                replica_status = "N/A"
            #grab configmaps and add to list
            try:
                for cm in container.env_from:
                    cm_list.append(cm.config_map_ref.name)
            except:
                cm_list = "N/A"
            #append required info to deployment_list           
            deployment_list.append([
                container.name,
                container.image,
                cm_list,
                replica_status,
                port_dict['app_protocol'],
                port_dict['name'],
                port_dict['node_port'],
                port_dict['port'],
                port_dict['protocol'],
                port_dict['target_port']
                ])
        return deployment_list
        

class TableModel(QAbstractTableModel):

    def __init__(self, data):
        super(TableModel, self).__init__()
        self._data = data

    def data(self, index, role):
        if role == Qt.ItemDataRole.DisplayRole:
            value = self._data.iloc[index.row(), index.column()]
            return str(value)

    def rowCount(self, index):
        return self._data.shape[0]

    def columnCount(self, index):
        return self._data.shape[1]
    #this allows user to edit fields on table
    def flags(self, index):
        return Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsEditable
    
    def headerData(self, section, orientation, role):
        # section is the index of the column/row.
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                return str(self._data.columns[section])
            
            if orientation == Qt.Orientation.Vertical:
                return str(self._data.index[section])
    #currently not in use, but this will save changes to data of table       
    def setData(self, index, value, role):
        if role == Qt.ItemDataRole.EditRole:
            # Set the value into the frame.
            self._data.iloc[index.row(), index.column()] = value
            return True

        return False


class MainWindow(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        #self.kube = Kube("~/Documents/Devops/configs/MAI/microai_stg_config")
        self.filename = None
        #main window settings
        self.setWindowTitle('Kubernetes Manager')
        self.setGeometry(100, 100, 1280, 720)
        #table settings
        self.table = QTableView()
        #layout for config file stuff
        layout = QGridLayout()
        self.setLayout(layout)
        self.layout().setAlignment(Qt.AlignmentFlag.AlignTop)

        #table settings
        self.table.setShowGrid(False)
        # file selection
        file_browser_btn = QPushButton('Browse')
        file_browser_btn.clicked.connect(self.open_file_dialog)
        #open file and show deployment info
        file_open_btn = QPushButton('Open')
        file_open_btn.clicked.connect(self.open_file)
        #apply button, apply changes to kubernetes cluster
        apply_btn = QPushButton('Apply')
        #creates textbox that shows file selected
        self.file_list = QListWidget(self)
        self.file_list.setFixedHeight(20)
        
        layout.addWidget(QLabel('ConfigFile:'), 0, 0)
        layout.addWidget(self.file_list, 0, 1)
        layout.addWidget(file_open_btn, 0 ,2)
        layout.addWidget(file_browser_btn, 0 ,3)
        layout.addWidget(self.table, 1, 0, 1, 4)
        layout.addWidget(apply_btn, 2, 3)
        
        self.show()

    def open_file_dialog(self):
        dialog = QFileDialog(self)
        dialog.setDirectory(r'~/')
        dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
        dialog.setNameFilter("Images ()")
        dialog.setViewMode(QFileDialog.ViewMode.List)
        if dialog.exec():
            filenames = dialog.selectedFiles()
            if filenames:
                self.file_list.addItems([str(Path(filename)) for filename in filenames])
                self.filename = [str(Path(filename)) for filename in filenames][0]
    
    def open_file(self):
        #initialize kubernetes class
        kube = Kube(self.filename)
        #create data table used in making the table
        data = pd.DataFrame(kube.getDeployments(), columns = 
                            ['Deployment', 'Image', 'ConfigMap', 'Status', 
                             'app protocol', 'port name', 'node_port', 'port', 'protocol', 'target port'])
        self.model = TableModel(data)
        self.table.setModel(self.model)
        self.table.resizeColumnsToContents()
        
        
if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    sys.exit(app.exec())