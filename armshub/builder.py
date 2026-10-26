"""Build one measured ArmsHub VPK from reusable arm sources and editor profiles."""
from dataclasses import asdict
import json
from pathlib import Path
import re
import tempfile

from charmstudio.natural_profile import (arms_entries, find_weapon_script,
                                        resources_with_game_fallback)
from charmstudio.project import Placement, digest
from charmstudio.resources import Resources
from charmstudio.source import Model
from .archive import write_shared_vpk
from .models import compile_bank, profile_files, charm_key
from .procedural import MODES

SURVIVORS = {
    'Gambler': ('Nick','models/weapons/arms/v_arms_gambler_new.mdl'),
    'Producer': ('Rochelle','models/weapons/arms/v_arms_producer_new.mdl'),
    'Coach': ('Coach','models/weapons/arms/v_arms_coach_new.mdl'),
    'Mechanic': ('Ellis','models/weapons/arms/v_arms_mechanic_new.mdl'),
    'NamVet': ('Bill','models/weapons/arms/v_arms_bill.mdl'),
    'TeenGirl': ('Zoey','models/weapons/arms/v_arms_zoey.mdl'),
    'Biker': ('Francis','models/weapons/arms/v_arms_francis.mdl'),
    'Manager': ('Louis','models/weapons/arms/v_arms_louis.mdl'),
}


def patch_armshub_script(data,replacements):
    slots=arms_entries(data)
    if set(replacements)!={name for name,_,_ in slots}:
        raise ValueError('Falta una variante de superviviente en ArmsHub')
    for name,_,(start,end) in reversed(slots):
        path=replacements[name]
        if not re.fullmatch(r'models/armshub/p_[0-9a-f]{16}\.mdl',path):
            raise ValueError('Ruta de perfil ArmsHub inválida')
        data=data[:start]+b'"'+path.encode()+b'"'+data[end:]
    return data


def detect_arms(mount):
    """Canonical replacements are unambiguous; custom paths require manual choice."""
    return {key:path for key,(_,path) in SURVIVORS.items() if path in mount.files}


def exact_mount(resources, model_path, sha):
    for mount in reversed(resources.mounts):
        if model_path in mount.files and digest(mount.read(model_path))==sha:
            return mount
    raise ValueError('Añade el VPK exacto del modelo del perfil: '+model_path)


def build(resources, profiles, assignments, compiler, destination, workspace, *, procedural_mode='repair'):
    if procedural_mode not in MODES:raise ValueError('Modo de huesos no válido')
    if not profiles:
        raise ValueError('Añade al menos un perfil JSON creado en Charm Studio')
    compiler = Path(compiler).resolve()
    if not compiler.is_file():
        raise ValueError('Selecciona studiomdl.exe de L4D2 Authoring Tools')
    resolved = resources_with_game_fallback(resources,compiler.parent.parent)
    groups, scripts, entries = {}, {}, []
    for profile in profiles:
        profile.validate()
        wm = exact_mount(resolved,profile.weapon,profile.weapon_sha256)
        cm = exact_mount(resolved,profile.charm,profile.charm_sha256)
        weapon = Model(resolved.reader(wm),profile.weapon,geometry=False)
        if profile.bone not in [bone.name for bone in weapon.bones]:
            raise ValueError('No existe el hueso '+profile.bone+' en '+profile.weapon)
        path, script, source = find_weapon_script(resolved,wm,profile.weapon)
        if path in scripts:
            raise ValueError('Solo un perfil por arma: '+path)
        scripts[path] = dict(original=script,replacements={},profile=asdict(profile))
        for survivor, original_arms, _ in arms_entries(script):
            if survivor in assignments:
                arms_source, arms_path = assignments[survivor]
                am = resolved.mount(arms_source)
            else:
                arms_path = original_arms
                am = next((m for m in reversed(resolved.mounts) if arms_path in m.files),None)
                if am is None:raise ValueError('Faltan brazos: '+arms_path)
            group = (str(am.path),arms_path)
            if group not in groups:
                groups[group] = dict(mount=am,path=arms_path,charms={},targets=set(),uses=[])
            key = charm_key(profile)
            groups[group]['charms'][key] = (cm,profile)
            groups[group]['targets'].add(profile.bone)
            use = dict(script=path,survivor=survivor,profile=profile)
            groups[group]['uses'].append(use)
            entries.append(dict(survivor=survivor,arms=arms_path,source=str(am.path),script=path))
    files, banks = {}, []
    for group in groups.values():
        mount = group['mount'];read = resolved.reader(mount)
        arms = Model(read,group['path'])
        charms = {key:(Model(resolved.reader(cm),p.charm),resolved.reader(cm),p)
                  for key,(cm,p) in group['charms'].items()}
        official = mount.path.parent.name.lower() in ('update','left4dead2','left4dead2_dlc1','left4dead2_dlc2','left4dead2_dlc3')
        bank = compile_bank(arms,read,charms,group['targets'],compiler,workspace,
                            pack_arms=not official,procedural_mode=procedural_mode)
        for use in group['uses']:
            p = use['profile']
            ident = digest(json.dumps([asdict(p),use['survivor'],bank.path],sort_keys=True).encode())[:16]
            model_path = f'models/armshub/p_{ident}.mdl'
            result = profile_files(bank,p,model_path)
            for name,data in result.items():
                if name in files and files[name]!=data:raise ValueError('Colisión de recursos: '+name)
                files[name] = data
            scripts[use['script']]['replacements'][use['survivor']] = model_path
        banks.append(dict(arms=group['path'],source=str(mount.path),charms=len(charms),
                          profiles=len(group['uses']),bones=len(Model(bank.files.__getitem__,bank.path,geometry=False).bones),
                          compiler_log=str(bank.build/'compiler.log'),procedural_events=bank.procedural_events))
    for path,info in scripts.items():files[path] = patch_armshub_script(info['original'],info['replacements'])
    files['addoninfo.txt'] = b'"AddonInfo" { "addonSteamAppID" "550" "addonTitle" "ArmsHub 0.3.2 EXPERIMENTAL" "addonVersion" "0.3.2" "addonAuthor" "ArmsHub" }\n'
    manifest = dict(schema=1,experimental=True,profiles=[asdict(p) for p in profiles],banks=banks,
        assignments=assignments,geometry_sharing='Identical whole VVD/VTX payloads share physical VPK ranges',
        hiding='Inactive charm materials use $no_draw; geometry and bones remain loaded',
        runtime_verified=False,online_verified=False,weapon_mesh_included=False,procedural_mode=procedural_mode)
    files['armshub/manifest.json'] = json.dumps(manifest,indent=2).encode('utf8')
    output = Path(destination);output.mkdir(parents=True,exist_ok=True)
    # Stage output first: failed builds leave the previous export usable.
    with tempfile.TemporaryDirectory(dir=output) as temporary:
        temporary = Path(temporary)
        stats = write_shared_vpk(temporary/'armshub_charms.vpk',files)
        report = dict(asdict(stats),profile_count=len(profiles),bank_count=len(banks),
            saved_percent_of_logical_payload=round(100*stats.saved_payload_bytes/max(1,stats.logical_payload_bytes),2),
            comparison='Same geometry-bank files packed with and without identical-file sharing; not a comparison against separate lean charm models',
            runtime_verified=False,online_verified=False,banks=banks,procedural_mode=procedural_mode,
            omitted_procedures=[dict(event,source=b['source']) for b in banks
                                for event in b['procedural_events'] if event['action']=='omitted'])
        (temporary/'armshub_report.json').write_text(json.dumps(report,indent=2),encoding='utf8')
        (temporary/'armshub_project.json').write_text(json.dumps(dict(schema=1,
            sources=[str(m.path) for m in resources.mounts],assignments=assignments,
            profiles=[asdict(p) for p in profiles],compiler=str(compiler),procedural_mode=procedural_mode),indent=2),encoding='utf8')
        for name in ['armshub_charms.vpk','armshub_report.json','armshub_project.json']:
            (temporary/name).replace(output/name)
    (output/'LEEME_ArmsHub.txt').write_text(
        'ARMSHUB 0.3.2: PROTOTIPO EXPERIMENTAL SEPARADO\n\n'
        'Modo procedural: '+procedural_mode+'\n'
        'Arreglar conserva reglas compatibles (tipos 1, 2 y jiggle 5), con referencias adaptadas.\n'
        'No arreglar omite las reglas especiales distintas de jiggle; el movimiento de manos puede cambiar.\n'
        'El informe enumera los procedimientos conservados u omitidos. Nunca se modifican los VPK originales.\n\n'
        'Importa los VPK de personajes y perfiles JSON de Charm Studio. Asigna sus brazos por superviviente.\n'
        'Al añadir o quitar perfiles, genera otra vez el mismo paquete armshub_charms.vpk.\n'
        'Mantén tus armas de Workshop. Este paquete no copia sus modelos. No usa DLL ni -insecure.\n'
        'Los materiales de brazos de mods se incluyen con sus dependencias reconocidas; los brazos originales usan materiales del juego.\n'
        'Brazos LOD0; sin variantes de skins/bodygroups en este prototipo. Máximo 128 huesos por banco.\n\n'
        'AHORRO: los VVD/VTX idénticos se almacenan físicamente una sola vez dentro del VPK.\n'
        'Cada perfil conserva su MDL pequeño. El banco contiene TODOS los charms elegidos para esos brazos.\n'
        'Los inactivos se ocultan por material, no se eliminan. Esto NO acredita ahorro de RAM/GPU.\n'
        'El informe compara el mismo banco con y sin reutilización de archivos idénticos.\n'
        'Una exportación individual con un solo charm puede ser menor que el banco; compara el conjunto completo.\n\n'
        'VALIDACIÓN: consulta el informe de pruebas del prototipo; no presupongas validación en juego por compilar.\n'
        'La compatibilidad online sigue pendiente y se respetan las restricciones de addons del servidor.\n'
        'Para una prueba manual, desactiva otros VPK de charms que cambien los mismos scripts, copia este VPK a addons y reinicia desde Steam.\n'
        'No se instala automáticamente ni modifica los VPK originales.\n',encoding='utf8')
    return report
