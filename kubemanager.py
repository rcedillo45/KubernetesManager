#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Feb 23 11:08:59 2023

@author: ricardoc
Kubernetes Management Tool
"""

import sys
from PyQt6.QtGui import QColor
from PyQt6.QtCore import Qt, QAbstractTableModel
from PyQt6.QtWidgets import (
    QApplication, 
    QWidget, 
    QFileDialog, 
    QGridLayout,
    QPushButton, 
    QLabel,
    QListWidget,
    QMenu,
    QTableWidget,
    QTableWidgetItem,
)
from pathlib import Path
import pandas as pd
from kubernetes import client, config
from kubernetes.client.rest import ApiException

class Kube:
    def __init__(self, path):
        self.path = path
        #load kube config file to gain access to kubernetes api clients
        config.load_kube_config(config_file=self.path)
        #loading necessary api clients
        self.core_api = client.CoreV1Api()
        self.app_api = client.AppsV1Api()
        self.networkapi = client.NetworkingV1Api()
        
    def getDeployments(self):
        #grab list of deployments
        deps = self.app_api.list_namespaced_deployment(namespace='application').items
        #grab list of services
        services = self.core_api.list_namespaced_service('application').items
        #this list will be returned
        networks = self.networkapi.list_ingress_for_all_namespaces()
        all_networks = []
        for network in networks.items:
            for rule in network.spec.rules:
                all_networks.append(rule)
        deployment_list = []
        for dep in deps:
            host = None
            cm_list = []
            ports = ''
            port_dict = {'app_protocol': [], 'name': [], 'node_port': [], 'port': [], 'protocol': [], 'target_port': []}
            #only need container spec for this function
            container = dep.spec.template.spec.containers[0]
            #loop through services and grab the service that matches container
            for service in services:
                if container.name == list(service.spec.selector.values())[0]:
                    ports = service.spec.ports
                    for port in ports:
                        current_port = port.to_dict()
                        for key, value in current_port.items():
                            port_dict[key].append(value)
                    for network in all_networks:
                        if service.metadata.name == network.http.paths[0].backend.service.name:
                            host = network.host
            
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
                host,
                port_dict['app_protocol'],
                port_dict['name'],
                port_dict['node_port'],
                port_dict['port'],
                port_dict['protocol'],
                port_dict['target_port']
                ])
        return deployment_list
    
    def getConfigMap(self, name):
        cm_list = self.core_api.list_config_map_for_all_namespaces().items
        for cm in cm_list:
            try:
                if cm.metadata.name == name:
                    config_map_data = list(cm.data.items())
                    return config_map_data
            except:
                pass
        return []  # Return an empty list if config map not found

        
    def getCMnames(self):
        cm_list = self.core_api.list_config_map_for_all_namespaces().items
        names = []
        for cm in cm_list:
            names.append(cm.metadata.name)
        return names
    
    def update_config_map_data(self, config_map_name, data):
        # Retrieve all namespaces
        try:
            namespaces = self.core_api.list_namespace().items
            print(config_map_name)
        except ApiException as e:
            print(f"Error retrieving namespaces: {e}")
            return False
    
        # Iterate over each namespace and update the ConfigMap
        for namespace in namespaces:
            # Read the existing ConfigMap
            try:
                config_map = self.core_api.read_namespaced_config_map(config_map_name, namespace.metadata.name)
            except ApiException as e:
                print(f"Error reading ConfigMap in namespace {namespace.metadata.name}: {e}")
                continue
    
            # Update the data in the ConfigMap
            config_map.data = data
    
            # Update the ConfigMap on the Kubernetes server
            try:
                self.core_api.replace_namespaced_config_map(config_map_name, namespace.metadata.name, body=config_map)
                print(f"ConfigMap {config_map_name} updated in namespace {namespace.metadata.name}")
            except ApiException as e:
                print(f"Error updating ConfigMap in namespace {namespace.metadata.name}: {e}")
    
        return True

class DeploymentWindow(QWidget):
    def __init__(self):
        super().__init__()
        layout = QGridLayout()
        self.table = QTableWidget()
        data = pd.DataFrame(kube.getDeployments(), columns=['Deployment', 'Image', 'ConfigMap', 'Status', 'Host',
                                                            'app protocol', 'port name', 'node_port', 'port', 'protocol', 'target port'])

        self.table.setRowCount(data.shape[0])
        self.table.setColumnCount(data.shape[1])
        self.table.setHorizontalHeaderLabels(data.columns)

        for row_idx, row_data in data.iterrows():
            for col_idx, cell_data in enumerate(row_data):
                item = QTableWidgetItem(str(cell_data))
                self.table.setItem(row_idx, col_idx, item)

        self.table.resizeColumnsToContents()
        layout.addWidget(self.table)
        self.setLayout(layout)

class ConfigWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.selected_config_map = None
        self.original_data = None  # Original data from the config map
        self.modified_data = None  # Modified data in the table
        self.btnOne = QPushButton(text="Select a Configmap", parent=self)
        self.menu = QMenu(self)
        cm_list = kube.getCMnames()
        for name in cm_list:
            action = self.menu.addAction(name)
            action.triggered.connect(lambda checked, name=name: self.menu_option_selected(name))
            
        self.btnOne.setMenu(self.menu)

        layout = QGridLayout()
        layout.addWidget(self.btnOne)
        self.setLayout(layout)
        
        self.table = QTableWidget(self)
        layout.addWidget(self.table)
        
        self.apply_button = QPushButton("Apply Changes")
        self.apply_button.clicked.connect(self.apply_changes)
        layout.addWidget(self.apply_button)
        
        # Connect cellChanged signal to update_modified_data slot
        self.table.cellChanged.connect(self.update_modified_data)
        
    def menu_option_selected(self, option_name):
        self.selected_config_map = option_name
        self.original_data = pd.DataFrame(kube.getConfigMap(option_name), columns=['Key', 'Value'])
        
        self.table.clearContents()
        self.table.setRowCount(0)
    
        self.table.setRowCount(self.original_data.shape[0])
        self.table.setColumnCount(self.original_data.shape[1])
    
        for row_idx, row_data in self.original_data.iterrows():
            for col_idx, cell_data in enumerate(row_data):
                item = QTableWidgetItem(str(cell_data))
                self.table.setItem(row_idx, col_idx, item)
    
        self.table.resizeColumnsToContents()
        
        # Initialize modified_data as a copy of original_data
        self.modified_data = self.original_data
        
    def update_modified_data(self, row, column):
        if self.modified_data is not None:
            # Get the modified value from the cell
            item = self.table.item(row, column)
            if item is not None:
                modified_value = item.text()
                
                # Update the corresponding cell in modified_data
                self.modified_data.iloc[row, column] = modified_value
            else:
                # Handle case when the item is None (e.g., cell was cleared)
                self.modified_data.iloc[row, column] = ""
            print(self.modified_data)
        
    def apply_changes(self):
        if not self.selected_config_map:
            print("No ConfigMap selected.")
            return

        print(self.selected_config_map)
        print(self.modified_data)

        success = kube.update_config_map_data(self.selected_config_map, self.modified_data.set_index('Key').squeeze().to_dict())
        
        if success:
            print(f"ConfigMap '{self.selected_config_map}' updated successfully")
        else:
            print(f"Failed to update ConfigMap '{self.selected_config_map}'")

class MainWindow(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.filename = None
        #main window settings
        self.setWindowTitle('Kubernetes Manager')
        self.setGeometry(100, 100, 600, 100)
        #layout for config file stuff
        layout = QGridLayout()
        self.setLayout(layout)
        self.layout().setAlignment(Qt.AlignmentFlag.AlignTop)
        # file selection
        file_browser_btn = QPushButton('Browse')
        file_browser_btn.clicked.connect(self.open_file_dialog)
        #open file and show deployment info
        file_open_btn = QPushButton('Open')
        file_open_btn.clicked.connect(self.open_file)
        #button to show deployment information
        deployments_btn = QPushButton('Deployments')
        deployments_btn.setFixedWidth(100)
        deployments_btn.clicked.connect(self.open_deployments)
        #button to show configmap information
        configmap_btn = QPushButton('Configmaps')
        configmap_btn.setFixedWidth(100)
        configmap_btn.clicked.connect(self.open_configmap)
        #apply button, apply changes to kubernetes cluster
        apply_btn = QPushButton('Apply')
        #creates textbox that shows file selected
        self.file_list = QListWidget(self)
        self.file_list.setFixedHeight(20)
        
        layout.addWidget(QLabel('ConfigFile:'), 0, 0)
        layout.addWidget(self.file_list, 0, 1)
        layout.addWidget(file_open_btn, 0 ,2)
        layout.addWidget(file_browser_btn, 0 ,3)
        layout.addWidget(deployments_btn, 1, 0)
        layout.addWidget(configmap_btn, 1, 1)
        layout.addWidget(apply_btn, 2, 3)

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
        global kube
        kube = Kube(self.filename)
    
    def open_deployments(self, checked):
        self.w = DeploymentWindow()
        self.w.show()
    
    def open_configmap(self, checked):
        self.w = ConfigWindow()
        self.w.show()
        
if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())