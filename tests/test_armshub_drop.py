import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import tempfile
import unittest
import json
from dataclasses import asdict,replace

from PyQt6.QtCore import QMimeData,QPoint,QPointF,QUrl,Qt
from PyQt6.QtGui import QDragEnterEvent,QDropEvent
from PyQt6.QtWidgets import QApplication

from armshub.app import ArmsHubWindow
from armshub.builder import SURVIVORS
from charmstudio.vpk import write_vpk
from charmstudio.project import Placement


class DropVpkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.window=ArmsHubWindow(self.root);self.errors=[]
        self.window.error=self.errors.append

    def tearDown(self):self.window.close();self.temp.cleanup()

    def archive(self,name,files):
        path=self.root/name;write_vpk(path,files);return path

    def drop(self,target,paths):
        mime=QMimeData();mime.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
        enter=QDragEnterEvent(QPoint(5,5),Qt.DropAction.CopyAction,mime,
                              Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(target,enter)
        if not enter.isAccepted():return False
        drop=QDropEvent(QPointF(5,5),Qt.DropAction.CopyAction,mime,
                        Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(target,drop)
        return drop.isAccepted()

    def test_drop_multiple_numeric_vpks_identifies_all_eight_without_filename_guessing(self):
        paths=[]
        for i,(key,(_,model)) in enumerate(SURVIVORS.items()):
            paths.append(self.archive(str(10000000+i)+'.VPK',{model:b'model source'}))
        self.assertTrue(self.drop(self.window,paths))
        self.assertEqual(set(self.window.assignments),set(SURVIVORS))
        self.assertFalse(self.errors)
        for key,(source,model) in self.window.assignments.items():
            self.assertEqual(model,SURVIVORS[key][1])
            self.assertIn(SURVIVORS[key][0],self.window.log.toPlainText())

    def test_drop_on_table_viewport_duplicate_import_and_explicit_conflict_choices(self):
        model=SURVIVORS['Gambler'][1]
        old=self.archive('old.vpk',{model:b'old'});new=self.archive('new.vpk',{model:b'new'})
        self.assertTrue(self.drop(self.window.arms.viewport(),[old]))
        self.assertTrue(self.drop(self.window.table.viewport(),[old]))
        self.assertEqual(len(self.window.resources.mounts),1)
        conflicts=[]
        def keep(mount,keys):conflicts.append(keys);return False
        self.window.replace_arm_conflicts=keep
        self.assertTrue(self.drop(self.window.drop_zone,[new]))
        self.assertEqual(conflicts,[['Gambler']])
        self.assertEqual(self.window.assignments['Gambler'][0],str(old.resolve()))
        self.window.replace_arm_conflicts=lambda mount,keys:True
        self.assertTrue(self.drop(self.window.log.viewport(),[new]))
        self.assertEqual(self.window.assignments['Gambler'][0],str(new.resolve()))

    def test_other_files_and_bad_vpk_do_not_prevent_remaining_imports(self):
        unknown=self.archive('weapon_001.vpk',{'models/v_models/v_rifle.mdl':b'weapon'})
        txt=self.root/'note.txt';txt.write_text('not a VPK')
        self.assertFalse(self.drop(self.window,[txt]))
        self.assertTrue(self.drop(self.window,[unknown,txt]))
        self.assertFalse(self.window.assignments)
        self.assertIn('Sin brazos reconocidos',self.window.log.toPlainText())
        bad=self.root/'broken.vpk';bad.write_bytes(b'broken')
        valid=self.archive('coach.vpk',{SURVIVORS['Coach'][1]:b'arms'})
        self.assertTrue(self.drop(self.window,[bad,valid]))
        self.assertIn('Coach',self.window.assignments)
        self.assertEqual(len(self.errors),1)

    def test_numbered_piece_resolves_directory_and_rejects_remote_urls(self):
        index=self.archive('pack_dir.vpk',{SURVIVORS['Producer'][1]:b'arms'})
        piece=self.root/'pack_000.vpk';piece.write_bytes(b'raw archive chunk')
        self.assertTrue(self.drop(self.window,[piece]))
        self.assertEqual(self.window.assignments['Producer'][0],str(index.resolve()))
        mime=QMimeData();mime.setUrls([QUrl('https://example.com/character.vpk')])
        self.assertEqual(self.window.dropped_files(mime),[])

    def test_file_drag_never_reports_a_move_to_explorer(self):
        path=self.archive('nick.vpk',{SURVIVORS['Gambler'][1]:b'arms'})
        mime=QMimeData();mime.setUrls([QUrl.fromLocalFile(str(path))])
        actions=Qt.DropAction.CopyAction|Qt.DropAction.MoveAction
        enter=QDragEnterEvent(QPoint(5,5),actions,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.ShiftModifier)
        self.window.dragEnterEvent(enter)
        self.assertTrue(enter.isAccepted());self.assertEqual(enter.dropAction(),Qt.DropAction.CopyAction)
        move_only=QDropEvent(QPointF(5,5),Qt.DropAction.MoveAction,mime,
                            Qt.MouseButton.LeftButton,Qt.KeyboardModifier.ShiftModifier)
        self.window.dropEvent(move_only)
        self.assertFalse(move_only.isAccepted());self.assertTrue(path.is_file())

    def profile(self,name='profile.json',weapon='models/v_models/v_rifle.mdl',**changes):
        profile=Placement(weapon,'0'*64,'models/charms/demo.mdl','1'*64,
                          'demo','ValveBiped.weapon_bone',[1,2,3],[0,0,180],1,'demo')
        profile=replace(profile,**changes)
        path=self.root/name;profile.save(path)
        return path,profile

    def test_json_profiles_and_vpks_can_be_dropped_together_on_a_table(self):
        a,p=self.profile('first.JSON')
        b,q=self.profile('second.json',weapon='models/v_models/v_shotgun_chrome.mdl')
        vpk=self.archive('nick.vpk',{SURVIVORS['Gambler'][1]:b'arms'})
        self.assertTrue(self.drop(self.window.table.viewport(),[a,vpk,b]))
        self.assertEqual(self.window.profiles,[p,q]);self.assertIn('Gambler',self.window.assignments)
        self.assertTrue(self.drop(self.window,[a]))
        self.assertEqual(len(self.window.profiles),2);self.assertFalse(self.errors)

    def test_invalid_and_conflicting_json_keep_existing_profiles_and_add_valid_ones(self):
        a,p=self.profile();self.drop(self.window,[a])
        conflicting,_=self.profile('different.json',offset=[9,8,7])
        valid,q=self.profile('new.json',weapon='models/v_models/v_pistola.mdl')
        invalid=self.root/'bad.json';invalid.write_text('{ broken',encoding='utf8')
        unknown=self.root/'report.json';unknown.write_text('{"archive_bytes": 42}',encoding='utf8')
        self.drop(self.window,[conflicting,invalid,valid,unknown])
        self.assertEqual(self.window.profiles,[p,q]);self.assertEqual(len(self.errors),1)

    def test_project_drop_is_applied_before_other_sources_and_profiles(self):
        arms=self.archive('coach.vpk',{SURVIVORS['Coach'][1]:b'arms'})
        first,p=self.profile();second,q=self.profile('more.json',weapon='models/v_models/v_pistola.mdl')
        project=self.root/'saved.json'
        data=dict(schema=1,sources=[],assignments={},profiles=[asdict(p)],
                  compiler=str(self.root/'studiomdl.exe'),procedural_mode='skip')
        project.write_text(json.dumps(data),encoding='utf8')
        self.assertTrue(self.drop(self.window,[second,arms,project]))
        self.assertEqual(self.window.profiles,[p,q]);self.assertIn('Coach',self.window.assignments)
        self.assertEqual(self.window.procedural_mode.currentData(),'skip')
        # A broken project cannot partially replace the current session.
        data['sources']=[str(self.root/'missing.vpk')];project.write_text(json.dumps(data),encoding='utf8')
        self.drop(self.window,[project]);self.assertEqual(self.window.profiles,[p,q])
        self.assertIn('Coach',self.window.assignments)

    def test_multiple_projects_are_rejected_without_modifying_current_configuration(self):
        first,p=self.profile();self.drop(self.window,[first])
        data=dict(schema=1,sources=[],assignments={},profiles=[],compiler='studiomdl.exe')
        projects=[]
        for name in ['one.json','two.json']:
            path=self.root/name;path.write_text(json.dumps(data),encoding='utf8');projects.append(path)
        self.drop(self.window,projects);self.assertEqual(self.window.profiles,[p])
        self.assertEqual(len(self.errors),1)


if __name__=='__main__':unittest.main()
