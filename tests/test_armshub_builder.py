import unittest
from armshub.builder import patch_armshub_script


class ArmsHubScriptTests(unittest.TestCase):
    def test_patch_preserves_gameplay_values_and_comments(self):
        data=(b'WeaponData { "Damage" "58" "CharacterViewmodelAddon" {\n'
              b'"Gambler" "models/arms/nick.mdl" // keep\n} "clip_size" "40" }')
        model='models/armshub/p_0123456789abcdef.mdl'
        self.assertEqual(patch_armshub_script(data,{'Gambler':model}),
                         data.replace(b'models/arms/nick.mdl',model.encode()))
        with self.assertRaises(ValueError):patch_armshub_script(data,{'Gambler':'../escape.mdl'})
        with self.assertRaises(ValueError):patch_armshub_script(data,{})
