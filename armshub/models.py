"""Compile a common geometry bank and derive topology-preserving MDL profiles.

Hidden charms use MATERIAL_VAR_NO_DRAW; no mesh/vertex/LOD count is changed.
VVD/VTX files remain byte-identical. This does not deduplicate runtime GPU memory.
"""
from dataclasses import dataclass
import json
from pathlib import Path
import struct
import subprocess
import tempfile

import numpy as np

from charmstudio.bake import _materials
from charmstudio.charm_pose import reference_pose, reference_vertices, skin_directions
from charmstudio.native_adapter import (_bone_euler, _numbers, _quote,
    _namespace_materials)
from charmstudio.natural_arms import _arms_material_names
from charmstudio.project import digest
from charmstudio.source import Model, Reader, euler_quaternion
from charmstudio.transforms import transform
from .procedural import collect,restore

HIDDEN = 'armshub/hidden'
HIDDEN_VMT = b'"VertexLitGeneric" { "$model" "1" "$no_draw" "1" }\n'


def charm_key(profile):
    return digest(json.dumps([profile.charm_sha256, profile.charm_pose, profile.scale]).encode())[:16]


@dataclass
class Bank:
    path: str
    files: dict
    mounts: dict
    roots: dict
    build: Path
    procedural_events: list


def compile_bank(arms, arms_read, charms, targets, compiler, workspace, *, pack_arms=False, procedural_mode='repair'):
    """charms maps key -> (Model, read, Placement). Never writes installed files."""
    if arms.r.i(224) > 1:
        raise ValueError('ArmsHub 0.1 no admite varias familias de skins en brazos')
    count, offset = arms.r.unpack('ii', 232)
    if any(arms.r.i(offset+i*16+4) != 1 for i in range(count)):
        raise ValueError('ArmsHub 0.1 no admite alternativas de bodygroups en brazos')
    if not len(arms.triangles):
        raise ValueError('Los brazos no tienen geometría')
    identity = digest(arms.data+json.dumps([sorted(charms), sorted(targets),procedural_mode]).encode())[:16]
    path = f'models/armshub/b_{identity}.mdl'
    poses = arms.bind_pose()
    names = [b.name for b in arms.bones]
    parents = [b.parent for b in arms.bones]
    local = [np.linalg.inv(poses[b.parent])@poses[i] if b.parent >= 0 else poses[i]
             for i, b in enumerate(arms.bones)]
    if len(set(names)) != len(names) or any(n.startswith('AH_') for n in names):
        raise ValueError('Nombres de huesos ambiguos o reservados AH_')
    for name in sorted(targets):
        if name not in names:
            names.append(name); parents.append(-1); local.append(np.eye(4))
    merged = len(names)
    assets = {'materials/'+HIDDEN+'.vmt': HIDDEN_VMT}
    if pack_arms:
        materials, data = _materials(arms.data, arms_read)
        materials, data = _namespace_materials(materials, data, 'ah_arms_'+digest(arms.data)[:16])
        assets.update(data)
    else:
        materials = _arms_material_names(arms, arms_read)
    parts = [('arms', arms, arms.positions, arms.normals, materials, 0)]
    rules,events = collect(arms,{name:name for name in names[:len(arms.bones)]},mode=procedural_mode)
    mounts, roots = {}, {}
    for number, (key, (charm, read, profile)) in enumerate(sorted(charms.items())):
        profile.validate()
        pose = reference_pose(charm, profile.charm_pose)
        mount = len(names)
        names.append(f'AH_mount_{number}'); parents.append(-1); local.append(np.eye(4))
        mounts[key] = mount
        start = len(names)
        roots[key] = (start, len(charm.bones))
        for i, bone in enumerate(charm.bones):
            names.append(f'AH_c{number}_{i}_{bone.name}')
            parents.append(start+bone.parent if bone.parent >= 0 else mount)
            matrix = np.linalg.inv(pose[bone.parent])@pose[i] if bone.parent >= 0 else pose[i].copy()
            matrix = matrix.copy(); matrix[:3, 3] *= profile.scale
            local.append(matrix)
        charm_rules,charm_events=collect(charm,{bone.name:names[start+i] for i,bone in enumerate(charm.bones)},
                                         scale=profile.scale,mode=procedural_mode)
        rules.extend(charm_rules);events.extend(charm_events)
        mats, data = _materials(charm.data, read)
        mats, data = _namespace_materials(mats, data, 'ah_charm_'+key)
        for name, value in data.items():
            if name in assets and assets[name] != value:
                raise ValueError('Colisión de materiales: '+name)
            assets[name] = value
        parts.append(('charm_'+key, charm, reference_vertices(charm, profile.charm_pose)*profile.scale,
                      skin_directions(charm, pose, charm.normals), mats, start))
    if len(names) > 128:
        raise ValueError(f'La biblioteca necesita {len(names)} huesos; límite 128. Reduce los charms por banco.')
    nodes = [f'{i} {_quote(name)} {parent}' for i, (name, parent) in enumerate(zip(names, parents))]
    frames = [f'{i} {_numbers(m[:3,3])} {_numbers(_bone_euler(m))}' for i,m in enumerate(local)]
    skeleton = ['version 1','nodes',*nodes,'end','skeleton','time 0',*frames,'end']
    build = Path(workspace)/'.build/armshub'
    build.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=identity+'_', dir=build))
    game = work/'game';game.mkdir()
    install = Path(compiler).resolve().parent.parent
    if not (install/'left4dead2/bin').is_dir():
        raise ValueError('Selecciona studiomdl.exe de L4D2 Authoring Tools')
    (game/'gameinfo.txt').write_text('"GameInfo" { game "ArmsHub Lab" FileSystem { SteamAppId 550 ToolsAppId 563 SearchPaths { '+
        f'GameBin {_quote(install/"left4dead2/bin")} Game {_quote(game)} Game {_quote(install/"left4dead2")} }} }} }}',encoding='utf8')
    qc = [f'$modelname {_quote(path.removeprefix("models/"))}', '$upaxis Z', '$origin 0 0 0 0',
          '$scale 1','$cdmaterials ""','$surfaceprop "flesh"','$sequence "idle" "idle.smd" fps 30 loop']
    (work/'idle.smd').write_text('\n'.join(skeleton)+'\n',encoding='utf8')
    for name, model, vertices, normals, mats, shift in parts:
        smd = skeleton+['triangles']
        for tri, mat in zip(model.triangles, model.material_ids):
            smd.append(mats[int(mat)])
            for vertex in tri[[0,2,1]]:
                uv = model.uvs[vertex].copy();uv[1] = 1-uv[1]
                links = [(int(b)+shift,float(w)) for b,w in zip(model.bone_ids[vertex],model.weights[vertex]) if w>0]
                if not links:
                    raise ValueError('Vértice sin pesos')
                total = sum(w for _,w in links)
                smd.append(f'{links[0][0]} {_numbers(vertices[vertex])} {_numbers(normals[vertex])} {_numbers(uv)} {len(links)} '+
                           ' '.join(f'{b} {w/total:.9f}' for b,w in links))
        (work/(name+'.smd')).write_text('\n'.join(smd+['end'])+'\n',encoding='utf8')
        qc.append(f'$body {_quote(name)} {_quote(name+".smd")}')
    # Keep a real, permanently hidden mesh so the nodraw material survives compilation.
    hidden = skeleton+['triangles',HIDDEN]
    hidden += [f'0 {_numbers(v)} 0 0 1 0 0 1 0 1' for v in [(0,0,0),(.01,0,0),(0,.01,0)]]
    (work/'hidden.smd').write_text('\n'.join(hidden+['end'])+'\n',encoding='utf8')
    qc.append('$body "hidden" "hidden.smd"')
    qc += ['$bonemerge '+_quote(name) for name in names[:merged]]
    (work/'bank.qc').write_text('\n'.join(qc)+'\n',encoding='utf8')
    result = subprocess.run([str(compiler),'-game',str(game),str(work/'bank.qc')],cwd=work,
        capture_output=True,text=True,errors='replace',timeout=120,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    (work/'compiler.log').write_text(result.stdout+'\n'+result.stderr,encoding='utf8')
    if result.returncode:
        raise RuntimeError('Error de compilación: '+str(work/'compiler.log'))
    files = dict(assets)
    for suffix in ['.mdl','.vvd','.dx90.vtx','.dx80.vtx','.sw.vtx']:
        name = path.removesuffix('.mdl')+suffix
        if (game/name).is_file():files[name] = (game/name).read_bytes()
    if any(path.removesuffix('.mdl')+s not in files for s in ['.mdl','.vvd','.dx90.vtx']):
        raise RuntimeError('Faltan archivos compilados: '+str(work))
    files[path] = restore(files[path],rules)
    compiled = Model(files.__getitem__,path)
    if [b.name for b in compiled.bones] != names:
        raise ValueError('El compilador reorganizó huesos del banco')
    if len(compiled.triangles) != sum(len(p[1].triangles) for p in parts)+1:
        raise ValueError('El compilador cambió la topología')
    for name,data in files.items():
        if name.endswith('.vtx'):
            r = Reader(data)
            lods, replacements = r.unpack('ii',20)
            if lods != 1 or any(r.i(replacements+i*8) for i in range(lods)):
                raise ValueError('El banco requiere LOD0 sin reemplazos de materiales VTX')
    return Bank(path,files,mounts,roots,work,events)


def profile_files(bank, profile, model_path):
    """Only MDL metadata varies; all sidecar bytes remain identical to the bank."""
    key = charm_key(profile)
    canonical = Model(bank.files.__getitem__,bank.path)
    names = [b.name for b in canonical.bones]
    target = names.index(profile.bone)
    mount = bank.mounts[key]
    matrix = transform(profile.offset,profile.angles)
    rotation = np.asarray(_bone_euler(matrix))
    quaternion = euler_quaternion(rotation)
    mdl = bytearray(canonical.data)
    internal = model_path.removeprefix('models/').encode('ascii')
    if len(internal)>=64 or len(model_path)>=64:
        raise ValueError('Nombre de modelo demasiado largo')
    mdl[12:76] = internal.ljust(64,b'\0')
    bone = canonical.r.i(160)+mount*216
    struct.pack_into('<i',mdl,bone+4,target)
    struct.pack_into('<3f4f3f',mdl,bone+32,*matrix[:3,3],*quaternion,*rotation)
    # A Quaternion64 constant loses precision near half turns because w is
    # reconstructed from quantized xyz. Use the full-float bone/linear defaults
    # instead. A flags=0 track reads those defaults in L4D2 CalcBoneQuaternion
    # and CalcBonePosition. Keep the nextoffset and unused bytes unchanged so
    # every other track retains its original address and data.
    for animation in canonical.animations:
        reader, track, _ = canonical._anim_data(animation,0)
        while track is not None:
            index, flags, relative = reader.unpack('BBh',track)
            if index==mount:
                if reader is not canonical.r or flags not in (0,32) or animation['flags']&4:
                    raise ValueError('La animación del punto de montaje no puede adaptarse en esta versión de ArmsHub.')
                struct.pack_into('<B',mdl,track+1,0)
            track = track+relative if relative>0 else None
    h2 = canonical.r.i(400)
    if h2 and canonical.r.i(h2+16):
        linear = h2+canonical.r.i(h2+16)
        if canonical.r.i(linear)!=len(names):raise ValueError('Cache lineal inválida')
        for field,stride,fmt,values in [(8,4,'i',[target]),(12,12,'3f',matrix[:3,3]),
                                       (16,16,'4f',quaternion),(20,12,'3f',rotation)]:
            start = linear+canonical.r.i(linear+field)+mount*stride
            struct.pack_into('<'+fmt,mdl,start,*values)
    # Newly chosen parents must participate in the same bone-setup masks as
    # the child. They were not its ancestors when studiomdl built the bank.
    usage = canonical.r.i(bone+160) & 0x7ff00
    ancestor = target
    while ancestor>=0:
        address = canonical.r.i(160)+ancestor*216
        flags = canonical.r.i(address+160)|usage
        struct.pack_into('<i',mdl,address+160,flags)
        if h2 and canonical.r.i(h2+16):
            struct.pack_into('<i',mdl,linear+canonical.r.i(linear+4)+ancestor*4,flags)
        ancestor = canonical.bones[ancestor].parent
    hidden = canonical.materials.index(HIDDEN)
    count, offset = canonical.r.unpack('ii',232)
    for i in range(count):
        body = offset+i*16
        name = canonical.r.string(body+canonical.r.i(body))
        if not name.startswith('charm_') or name=='charm_'+key:continue
        if canonical.r.i(body+4)!=1:raise ValueError('Banco con variantes no admitidas')
        model = body+canonical.r.i(body+12)
        meshes, relative = canonical.r.unpack('ii',model+72)
        for j in range(meshes):struct.pack_into('<i',mdl,model+relative+j*116,hidden)
    files = {name:value for name,value in bank.files.items() if name.startswith('materials/')}
    stem = model_path.removesuffix('.mdl')
    original = bank.path.removesuffix('.mdl')
    for name,data in bank.files.items():
        if name.startswith(original+'.'):
            files[stem+name[len(original):]] = bytes(mdl) if name==bank.path else data
    compiled = Model(files.__getitem__,model_path)
    animated = compiled.pose(0,0)
    expected=animated[target]@matrix
    if not compiled.sequences or not compiled.sequences[0].supported or not np.allclose(
            animated[mount],expected,rtol=1e-7,atol=3e-5):
        difference=float(np.max(np.abs(animated[mount]-expected)))
        raise ValueError('La orientación exportada no coincide con el perfil '
                         f'(diferencia máxima: {difference:.6g}). No se generó el paquete.')
    if not np.allclose([b.pose_to_bone for b in compiled.bones],
                       [b.pose_to_bone for b in canonical.bones]):
        raise ValueError('Se modificaron las matrices inversas canónicas')
    # Include both canonical and moved poses in the conservative local bounds.
    vertices = compiled.skinned_vertices(compiled.bind_pose())
    minimum = np.minimum(vertices.min(axis=0),canonical.positions.min(axis=0))-1
    maximum = np.maximum(vertices.max(axis=0),canonical.positions.max(axis=0))+1
    for start in [104,128]:struct.pack_into('<6f',mdl,start,*minimum,*maximum)
    count, offset = canonical.r.unpack('ii',188)
    for index in range(count):struct.pack_into('<6f',mdl,offset+index*212+32,*minimum,*maximum)
    files[model_path] = bytes(mdl)
    return files
