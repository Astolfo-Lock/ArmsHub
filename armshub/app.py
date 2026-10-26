"""Small PyQt6 workbench for the separate ArmsHub experiment."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import json
from pathlib import Path

from PyQt6.QtCore import QTimer, Qt, QEvent
from PyQt6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,
    QPushButton,QLabel,QTableWidget,QTableWidgetItem,QFileDialog,QMessageBox,QInputDialog,
    QPlainTextEdit,QHeaderView,QComboBox)

from charmstudio.project import Placement
from charmstudio.resources import Resources
from . import VERSION
from .builder import SURVIVORS,detect_arms,build


class ArmsHubWindow(QMainWindow):
    def __init__(self,root):
        super().__init__()
        self.root=Path(root);self.resources=Resources();self.profiles=[];self.assignments={}
        self.compiler=Path(r'C:\Program Files (x86)\Steam\steamapps\common\Left 4 Dead 2\bin\studiomdl.exe')
        self.pool=ThreadPoolExecutor(max_workers=1);self.future=None
        self.setWindowTitle('ArmsHub '+VERSION+' · VPK y JSON arrastrables');self.resize(1040,880)
        central=QWidget();self.setCentralWidget(central);layout=QVBoxLayout(central)
        title=QLabel('ArmsHub · Brazos de tus personajes, perfiles de tus charms')
        title.setStyleSheet('font-size:19px;font-weight:bold;padding:10px');layout.addWidget(title)
        note=QLabel('Prototipo separado de Charm Studio. Importa sus perfiles JSON; aquí eliges los brazos y generas un único VPK.\n'
                    'Bancos separados por brazos y charm, con su pose y escala. Un único VPK. Validación online pendiente.')
        note.setWordWrap(True);layout.addWidget(note)
        self.drop_zone=QLabel('Arrastra tus .vpk y perfiles .json aquí o sobre las tablas.\n'
                             'También puedes soltar un proyecto ArmsHub para recuperar sus brazos y perfiles.')
        self.drop_zone.setWordWrap(True)
        self.drop_zone.setStyleSheet('border:2px dashed #6387aa;border-radius:6px;padding:12px;')
        layout.addWidget(self.drop_zone)
        row=QHBoxLayout();layout.addLayout(row)
        for label,callback in [('Añadir VPK de personajes o armas',self.add_sources),('Añadir perfiles JSON',self.add_profiles),
                               ('Abrir proyecto ArmsHub',self.open_project),('Elegir studiomdl.exe',self.choose_compiler)]:
            button=QPushButton(label);button.clicked.connect(callback);row.addWidget(button)
        layout.addWidget(QLabel('Brazos por superviviente · selecciona una fila para cambiar su asignación'))
        self.arms=QTableWidget(8,3);self.arms.setHorizontalHeaderLabels(['Superviviente','Modelo de brazos','Fuente'])
        self.arms.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.arms.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.arms.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.arms)
        row=QHBoxLayout();layout.addLayout(row)
        for label,callback in [('Asignar brazos de un addon',self.assign),('Usar brazos del juego',self.reset_arm)]:
            b=QPushButton(label);b.clicked.connect(callback);row.addWidget(b)
        layout.addWidget(QLabel('Perfiles · un charm por arma; la colocación se edita en Charm Studio'))
        self.table=QTableWidget(0,3);self.table.setHorizontalHeaderLabels(['Arma','Charm','Hueso'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers);layout.addWidget(self.table)
        remove=QPushButton('Quitar perfil seleccionado');remove.clicked.connect(self.remove_profile);layout.addWidget(remove)
        row=QHBoxLayout();layout.addLayout(row);row.addWidget(QLabel('Huesos procedurales:'))
        self.procedural_mode=QComboBox()
        self.procedural_mode.addItem('Arreglar hueso (conservar procedimientos compatibles)','repair')
        self.procedural_mode.addItem('No arreglar y seguir (omitir procedimientos especiales)','skip')
        row.addWidget(self.procedural_mode,1)
        self.procedural_note=QLabel();self.procedural_note.setWordWrap(True);layout.addWidget(self.procedural_note)
        self.procedural_mode.currentIndexChanged.connect(self.update_procedural_note)
        self.update_procedural_note()
        self.output=QPushButton('Generar o actualizar armshub_charms.vpk');self.output.clicked.connect(self.export);layout.addWidget(self.output)
        self.log=QPlainTextEdit();self.log.setReadOnly(True);self.log.setMaximumHeight(150);layout.addWidget(self.log)
        self.setAcceptDrops(True)
        # Scroll-area viewports otherwise consume drops instead of the main window.
        for target in [central,self.drop_zone,self.arms,self.arms.viewport(),
                       self.table,self.table.viewport(),self.log,self.log.viewport()]:
            target.setAcceptDrops(True);target.installEventFilter(self)
        for folder in sorted((self.root/'charms').glob('*')):
            if folder.is_dir():self.resources.mount(folder)
        self.timer=QTimer(self);self.timer.timeout.connect(self.poll);self.timer.start(150)
        self.refresh()

    def refresh(self):
        for row,(key,(name,default)) in enumerate(SURVIVORS.items()):
            source,model=self.assignments.get(key,('',default))
            for column,value in enumerate([name,model,Path(source).name if source else 'Juego (si no hay reemplazo seleccionado)']):
                self.arms.setItem(row,column,QTableWidgetItem(value))
        self.table.setRowCount(len(self.profiles))
        for row,p in enumerate(self.profiles):
            for col,value in enumerate([Path(p.weapon).stem,Path(p.charm).stem,p.bone]):
                self.table.setItem(row,col,QTableWidgetItem(value))

    def error(self,error):QMessageBox.warning(self,'ArmsHub',str(error))

    def update_procedural_note(self):
        self.procedural_note.setText(
            'Conserva las reglas de tipos 1 y 2 y adapta sus referencias para que L4D2 las calcule. Un tipo todavía no compatible detiene la exportación.'
            if self.procedural_mode.currentData()=='repair' else
            'Continúa sin las reglas especiales distintas de jiggle. Las manos pueden moverse diferente; el informe enumera los huesos afectados.')

    def add_sources(self):
        paths,_=QFileDialog.getOpenFileNames(self,'VPK de personajes, armas o charms','','Valve VPK (*.vpk)')
        if not paths:return
        self.import_sources(paths)

    @staticmethod
    def dropped_files(mime):
        if not mime.hasUrls():return []
        return list(dict.fromkeys(url.toLocalFile() for url in mime.urls()
                    if url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() in ('.vpk','.json')
                    and Path(url.toLocalFile()).is_file()))

    def handle_file_drag(self,event):
        paths=self.dropped_files(event.mimeData())
        if not paths or not event.possibleActions()&Qt.DropAction.CopyAction:
            event.ignore();return
        event.setDropAction(Qt.DropAction.CopyAction);event.accept()
        if event.type()==QEvent.Type.Drop:self.import_dropped_files(paths)

    def dragEnterEvent(self,event):self.handle_file_drag(event)

    def dragMoveEvent(self,event):self.handle_file_drag(event)

    def dropEvent(self,event):self.handle_file_drag(event)

    def eventFilter(self,target,event):
        if event.type() in (QEvent.Type.DragEnter,QEvent.Type.DragMove,QEvent.Type.Drop):
            self.handle_file_drag(event);return True
        return super().eventFilter(target,event)

    def replace_arm_conflicts(self,mount,conflicts):
        box=QMessageBox(self);box.setWindowTitle('Elegir brazos')
        names=', '.join(SURVIVORS[key][0] for key in conflicts)
        box.setText(mount.name+' incluye otros brazos para: '+names+'.\n\n'
                    '¿Qué brazos quieres conservar para esos supervivientes?')
        keep=box.addButton('Conservar los actuales',QMessageBox.ButtonRole.RejectRole)
        replace=box.addButton('Usar los del nuevo VPK',QMessageBox.ButtonRole.AcceptRole)
        box.setDefaultButton(keep);box.setEscapeButton(keep);box.exec()
        return box.clickedButton()==replace

    def import_sources(self,paths,*,show_errors=True):
        errors=[]
        for path in paths:
            try:
                path=Path(path)
                # Numbered pieces do not have a directory tree of their own.
                if len(path.stem)>4 and path.stem[-4]=='_' and path.stem[-3:].isdigit():
                    with path.open('rb') as file:has_header=file.read(4)==b'\x34\x12\xaa\x55'
                    if not has_header:
                        index=path.with_name(path.stem[:-4]+'_dir.vpk')
                        if not index.is_file():raise ValueError('Para un VPK dividido, añade su archivo *_dir.vpk.')
                        path=index
                mount=self.resources.mount(path)
                found=detect_arms(mount)
                conflicts=[key for key,model in found.items() if key in self.assignments
                           and self.assignments[key]!=(str(mount.path),model)]
                replace=bool(conflicts) and self.replace_arm_conflicts(mount,conflicts)
                assigned=[]
                for survivor,model in found.items():
                    if survivor not in conflicts or replace:
                        self.assignments[survivor]=(str(mount.path),model)
                        assigned.append(SURVIVORS[survivor][0])
                if assigned:self.log.appendPlainText(mount.name+' → Brazos asignados: '+', '.join(assigned))
                if conflicts and not replace:
                    self.log.appendPlainText('Se conservan los brazos actuales de: '+', '.join(SURVIVORS[key][0] for key in conflicts))
                if not found:
                    self.log.appendPlainText(mount.name+' → Sin brazos reconocidos; añadido como fuente para armas o charms. '
                                             'Si usa rutas de brazos personalizadas, utiliza «Asignar brazos de un addon».')
            except Exception as error:
                message=Path(path).name+': '+str(error);errors.append(message)
                self.log.appendPlainText('No se pudo añadir '+message)
        self.refresh()
        if errors and show_errors:self.error('\n\n'.join(errors[:5]))
        return errors

    @staticmethod
    def read_json(path):
        path=Path(path)
        if path.stat().st_size>8*1024*1024:raise ValueError('El JSON es demasiado grande')
        data=json.loads(path.read_text(encoding='utf-8-sig'))
        if not isinstance(data,dict):raise ValueError('El JSON debe contener un perfil o proyecto')
        return data

    def append_profile(self,profile):
        for previous in self.profiles:
            if previous.weapon.lower()!=profile.weapon.lower():continue
            if asdict(previous)==asdict(profile):
                self.log.appendPlainText('Perfil ya cargado: '+Path(profile.weapon).stem);return
            raise ValueError('Ya hay un perfil distinto para '+profile.weapon+'. Quita el anterior para sustituirlo.')
        self.profiles.append(profile)
        self.log.appendPlainText('Perfil añadido: '+Path(profile.weapon).stem+' → '+Path(profile.charm).stem)

    def import_dropped_files(self,paths):
        projects=[];profiles=[];vpks=[];errors=[]
        for path in paths:
            if Path(path).suffix.lower()=='.vpk':vpks.append(path);continue
            try:
                data=self.read_json(path)
                if 'sources' in data and 'profiles' in data:
                    projects.append((path,data))
                elif 'weapon' in data and 'charm' in data:
                    if Path(path).stat().st_size>65536:raise ValueError('Perfil demasiado grande')
                    profiles.append((path,Placement(**data).validate()))
                else:raise ValueError('Este JSON no es un perfil de Charm Studio ni un proyecto ArmsHub')
            except Exception as error:errors.append(Path(path).name+': '+str(error))
        if len(projects)>1:
            self.error('Suelta un solo proyecto ArmsHub por vez. Puedes acompañarlo de varios perfiles y VPK.');return
        # A project replaces the session; apply it first, then additional sources
        # and profiles, regardless of the order Explorer supplies the filenames.
        if projects:
            try:self.load_project(*projects[0])
            except Exception as error:
                self.error(Path(projects[0][0]).name+': '+str(error));return
        errors.extend(self.import_sources(vpks,show_errors=False))
        for path,profile in profiles:
            try:self.append_profile(profile)
            except Exception as error:errors.append(Path(path).name+': '+str(error))
        self.refresh()
        for error in errors:self.log.appendPlainText('No se pudo importar '+error)
        if errors:self.error('\n\n'.join(errors[:5]))

    def add_profiles(self):
        paths,_=QFileDialog.getOpenFileNames(self,'Perfiles JSON guardados por Charm Studio','','JSON (*.json)')
        errors=[]
        for path in paths:
            try:self.append_profile(Placement.load(path))
            except Exception as error:errors.append(Path(path).name+': '+str(error))
        self.refresh()
        if errors:self.error('\n\n'.join(errors[:5]))

    def assign(self):
        row=self.arms.currentRow()
        if row<0:self.error('Selecciona un superviviente');return
        candidates=[]
        for mount in self.resources.mounts:
            for path in mount.files:
                if path.endswith('.mdl') and ('/arms/' in path or '/hands/' in path or Path(path).stem.startswith(('arms','v_arms','hands','v_hands'))):
                    candidates.append((mount,path))
        if not candidates:self.error('Añade un VPK con modelos de brazos');return
        labels=[str(m.path)+' → '+p for m,p in candidates]
        selected,ok=QInputDialog.getItem(self,'Asignar brazos','Modelo de primera persona:',labels,0,False)
        if ok:
            mount,path=candidates[labels.index(selected)]
            self.assignments[list(SURVIVORS)[row]]=(str(mount.path),path);self.refresh()

    def reset_arm(self):
        row=self.arms.currentRow()
        if row>=0:self.assignments.pop(list(SURVIVORS)[row],None);self.refresh()

    def remove_profile(self):
        row=self.table.currentRow()
        if row>=0:self.profiles.pop(row);self.refresh()

    def choose_compiler(self):
        path,_=QFileDialog.getOpenFileName(self,'studiomdl.exe de L4D2 Authoring Tools',str(self.compiler),'studiomdl.exe (studiomdl.exe)')
        if path:self.compiler=Path(path)

    def open_project(self):
        path,_=QFileDialog.getOpenFileName(self,'Abrir armshub_project.json','','JSON (*.json)')
        if not path:return
        try:self.load_project(path)
        except Exception as e:self.error(e)

    def load_project(self,path,data=None):
        data=self.read_json(path) if data is None else data
        if data.get('schema')!=1:raise ValueError('Versión de proyecto no admitida')
        resources=Resources()
        for source in data['sources']:
            if not Path(source).exists():raise ValueError('No se encuentra la fuente del proyecto: '+str(source))
            resources.mount(source)
        profiles=[Placement(**p).validate() for p in data['profiles']]
        if len({p.weapon.lower() for p in profiles})!=len(profiles):
            raise ValueError('El proyecto contiene varios perfiles para la misma arma')
        if any(key not in SURVIVORS or not isinstance(value,(list,tuple)) or len(value)!=2
               or not all(isinstance(item,str) for item in value) for key,value in data['assignments'].items()):
            raise ValueError('Asignación de superviviente inválida')
        assignments={key:tuple(value) for key,value in data['assignments'].items()}
        mode=data.get('procedural_mode','repair')
        if mode not in ('repair','skip'):raise ValueError('Modo de huesos no válido')
        compiler=Path(data['compiler'])
        self.resources=resources;self.profiles=profiles;self.assignments=assignments
        self.compiler=compiler;self.refresh()
        self.procedural_mode.setCurrentIndex(self.procedural_mode.findData(mode))
        self.log.appendPlainText('Proyecto cargado: '+Path(path).name)

    def export(self):
        if self.future:return
        folder=QFileDialog.getExistingDirectory(self,'Carpeta de salida del prototipo',str(self.root/'dist'))
        if not folder:return
        self.output.setEnabled(False);self.procedural_mode.setEnabled(False)
        self.log.appendPlainText('Compilando bancos separados por brazos y charm. Los originales permanecen intactos…')
        snapshot=Resources();snapshot.mounts=list(self.resources.mounts)
        self.future=self.pool.submit(build,snapshot,list(self.profiles),dict(self.assignments),self.compiler,folder,self.root,
                                     procedural_mode=self.procedural_mode.currentData())

    def poll(self):
        if not self.future or not self.future.done():return
        future,self.future=self.future,None;self.output.setEnabled(True);self.procedural_mode.setEnabled(True)
        try:
            report=future.result();mib=1024*1024
            self.log.appendPlainText(f"Listo: {report['profile_count']} perfiles, {report['bank_count']} bancos por charm.\n"
                f"VPK físico: {report['archive_bytes']/mib:.2f} MiB. Datos lógicos: {report['logical_payload_bytes']/mib:.2f} MiB.\n"
                f"Reutilización de bytes idénticos: {report['saved_payload_bytes']/mib:.2f} MiB ({report['saved_percent_of_logical_payload']} %).\n"
                'Consulta armshub_report.json. Compilar no certifica renderizado ni compatibilidad online.')
            self.log.appendPlainText('Para usar el addon: copia el VPK, habilítalo en L4D2, cierra el juego por completo y vuelve a iniciarlo desde Steam.')
            omitted=report.get('omitted_procedures',[])
            self.log.appendPlainText('Modo de huesos: '+report.get('procedural_mode','repair')+
                                     '. Procedimientos omitidos: '+str(len(omitted)))
            for event in omitted:
                self.log.appendPlainText('Omitido: '+event['bone']+' (tipo '+str(event['type'])+') — '+event['model'])
        except Exception as e:self.error(e)

    def closeEvent(self,event):
        if self.future and not self.future.done():
            self.error('Espera a que termine la compilación antes de cerrar.');event.ignore();return
        self.pool.shutdown(wait=False);super().closeEvent(event)
