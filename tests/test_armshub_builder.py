from dataclasses import replace
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from armshub import builder
from armshub.builder import patch_armshub_script, SURVIVORS
from armshub.models import charm_key
from charmstudio.natural_profile import arms_entries
from charmstudio.project import Placement, digest
from charmstudio.resources import Resources
from charmstudio.vpk import VPK, write_vpk


class ArmsHubScriptTests(unittest.TestCase):
    def test_patch_preserves_gameplay_values_and_comments(self):
        data=(b'WeaponData { "Damage" "58" "CharacterViewmodelAddon" {\n'
              b'"Gambler" "models/arms/nick.mdl" // keep\n} "clip_size" "40" }')
        model='models/armshub/p_0123456789abcdef.mdl'
        self.assertEqual(patch_armshub_script(data,{'Gambler':model}),
                         data.replace(b'models/arms/nick.mdl',model.encode()))
        with self.assertRaises(ValueError):patch_armshub_script(data,{'Gambler':'../escape.mdl'})
        with self.assertRaises(ValueError):patch_armshub_script(data,{})


class PerCharmBuildTests(unittest.TestCase):
    """Exercise planning, script routing and packaging without game assets.

    Only binary model compilation/placement is substituted. Resource mounting,
    SHA checks, script discovery, all survivor slots and VPK output are real.
    """

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.compiler = self.root/'studiomdl.exe'
        self.compiler.write_bytes(b'not executed')
        self.resources = Resources()
        self.assignments = {}
        for survivor, (_, arms) in SURVIVORS.items():
            source = self.root/(survivor+'.vpk')
            write_vpk(source, {arms: ('arms '+survivor).encode()})
            self.resources.mount(source)
            self.assignments[survivor] = (str(source), arms)
        self.profiles = []
        files = {}
        for i in range(5):
            weapon = f'models/v_models/weapon_{i}.mdl'
            charm = 'models/charms/'+('bread' if i < 4 else 'medkit')+'.mdl'
            files[weapon] = weapon.encode()
            files[charm] = charm.encode()
            p = Placement(weapon, digest(files[weapon]), charm, digest(files[charm]),
                          'charm', 'target_'+str(i), [i, 2, 3], [0, 180, 0], 1., 'variant')
            if i == 2:
                p = replace(p, scale=.5)
            if i == 3:
                p = replace(p, charm_pose='sequence0')
            self.profiles.append(p.validate())
            slots = '\n'.join('"'+key+'" "'+arms+'" // preserved'
                              for key, (_, arms) in SURVIVORS.items())
            files[f'scripts/weapon_{i}.txt'] = (
                'WeaponData { "ViewModel" "'+weapon+'" "Damage" "58" '
                '"CharacterViewmodelAddon" {\n'+slots+'\n} "clip_size" "40" }').encode()
        source = self.root/'weapons_and_charms.vpk'
        write_vpk(source, files)
        self.resources.mount(source)
        self.original_scripts = {n: d for n, d in files.items() if n.startswith('scripts/')}

    def model(self, read, path, **kwargs):
        return SimpleNamespace(path=path, data=read(path),
                               bones=[SimpleNamespace(name=p.bone) for p in self.profiles])

    def compile(self, arms, read, charms, targets, compiler, workspace, **kwargs):
        self.assertEqual(len(charms), 1, 'Inactive charms must not enter a bank')
        key = next(iter(charms))
        expected_targets = {p.bone for p in self.profiles if charm_key(p) == key}
        self.assertEqual(set(targets), expected_targets)
        self.assertEqual(kwargs['procedural_mode'], self.mode)
        self.assertTrue(kwargs['pack_arms'])
        self.calls.append((arms.data, key))
        data = arms.data+b'|'+key.encode()
        path = 'models/armshub/b_'+digest(data)[:16]+'.mdl'
        work = self.root/'compiler_logs'
        return SimpleNamespace(path=path, files={path: data}, build=work,
                               procedural_events=[], key=key, data=data)

    def place(self, bank, profile, model_path):
        self.assertEqual(bank.key, charm_key(profile))
        data = bank.data+b'|'+json.dumps([profile.bone, profile.offset, profile.angles]).encode()
        return {model_path: data, model_path[:-4]+'.vvd': bank.data}

    def build(self, output):
        with patch.object(builder, 'resources_with_game_fallback', side_effect=lambda r, g: r), \
             patch.object(builder, 'Model', side_effect=self.model), \
             patch.object(builder, 'compile_bank', side_effect=self.compile), \
             patch.object(builder, 'profile_files', side_effect=self.place):
            return builder.build(self.resources, self.profiles, self.assignments,
                                 self.compiler, output, self.root, procedural_mode=self.mode)

    def test_separates_charms_pose_scale_and_reuses_placement_variants_for_all_survivors(self):
        before = {m.path: m.path.read_bytes() for m in self.resources.mounts}
        for mode in ('repair', 'skip'):
            with self.subTest(mode=mode):
                self.mode, self.calls = mode, []
                output = self.root/mode
                report = self.build(output)
                # Profiles 0/1 differ in weapon, bone and placement but share
                # geometry. Scale, pose and charm changes require other banks.
                self.assertEqual(report['bank_count'], 4*8)
                self.assertEqual(len(self.calls), 4*8)
                self.assertEqual(len(set(self.calls)), 4*8)
                self.assertTrue(all(b['charms'] == 1 for b in report['banks']))
                self.assertEqual(report['bank_strategy'], 'per_charm')
                self.assertFalse(report['inactive_charms_included'])
                archive = VPK(output/'armshub_charms.vpk')
                manifest = json.loads(archive.read('armshub/manifest.json'))
                self.assertEqual(manifest['bank_strategy'], 'per_charm')
                self.assertFalse(manifest['selective_loading'])
                self.assertFalse(manifest['weapon_mesh_included'])
                self.assertEqual(len([n for n in archive.entries if n.endswith('.mdl')]), 40)
                self.assertFalse(any(n.startswith('models/v_models/') for n in archive.entries))
                sidecars = {}
                for i, p in enumerate(self.profiles):
                    name = f'scripts/weapon_{i}.txt'
                    script = archive.read(name)
                    slots = arms_entries(script)
                    self.assertEqual({s for s, _, _ in slots}, set(SURVIVORS))
                    placeholders = {s: 'models/armshub/p_0000000000000000.mdl' for s in SURVIVORS}
                    self.assertEqual(patch_armshub_script(script, placeholders),
                                     patch_armshub_script(self.original_scripts[name], placeholders))
                    for survivor, path, _ in slots:
                        expected = ('arms '+survivor+'|'+charm_key(p)).encode()
                        self.assertEqual(archive.read(path), expected+b'|'+
                                         json.dumps([p.bone, p.offset, p.angles]).encode())
                        sidecars[i, survivor] = archive.entries[path[:-4]+'.vvd']
                for survivor in SURVIVORS:
                    self.assertEqual(sidecars[0, survivor].offset, sidecars[1, survivor].offset)
                    self.assertNotEqual(sidecars[0, survivor].offset, sidecars[2, survivor].offset)
                project = json.loads((output/'armshub_project.json').read_text(encoding='utf8'))
                self.assertEqual(project['schema'], 1)
                self.assertEqual(len(project['profiles']), 5)
                self.assertEqual(project['procedural_mode'], mode)
        self.assertEqual(before, {m.path: m.path.read_bytes() for m in self.resources.mounts})

    def test_failed_packaging_preserves_previous_export(self):
        self.mode, self.calls = 'repair', []
        output = self.root/'previous'
        output.mkdir()
        names = ('armshub_charms.vpk', 'armshub_project.json', 'armshub_report.json')
        before = {name: ('previous '+name).encode() for name in names}
        for name, data in before.items():
            (output/name).write_bytes(data)
        with patch.object(builder, 'write_shared_vpk', side_effect=OSError('disk full')):
            with self.assertRaisesRegex(OSError, 'disk full'):
                self.build(output)
        self.assertEqual(before, {name: (output/name).read_bytes() for name in names})
