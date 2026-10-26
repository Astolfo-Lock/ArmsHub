"""Relocate supported L4D2 procedural rules into a rebuilt skeleton.

Layouts: hl2sdk/l4d2/public/studio.h: axis interpolation (1), quaternion
interpolation (2), jiggle (5). Other rules stop repair mode; skip mode drops
non-jiggle rules explicitly and reports each affected bone.
"""
from dataclasses import dataclass
import struct

import numpy as np

from charmstudio.native_adapter import L4D2_JIGGLE
from charmstudio.natural_arms import _scaled_jiggle
from charmstudio.source import Model

MODES = ('repair','skip')


@dataclass(frozen=True)
class Rule:
    bone: str
    kind: int
    payload: bytes
    control: str | None = None


def collect(model, mapping, scale=1.0, mode='repair'):
    if mode not in MODES:raise ValueError('Modo de huesos no válido')
    rules,events=[],[]
    for index,bone in enumerate(model.bones):
        address=model.r.i(160)+index*216
        kind,relative=model.r.unpack('ii',address+164)
        if not kind:continue
        event=dict(model=model.path,bone=bone.name,type=kind,exported_bone=mapping[bone.name])
        if mode=='skip' and kind!=5:
            rules.append(Rule(mapping[bone.name],0,b''))
            events.append(dict(event,action='omitted'));continue
        if kind not in (1,2,5):
            raise ValueError(f'No se puede arreglar {bone.name}: procedimiento tipo {kind} no compatible. '
                             'Selecciona «No arreglar y seguir» para omitirlo.')
        start=address+relative
        if not relative or start<0 or start>=len(model.data):
            raise ValueError('Datos procedurales fuera del modelo: '+bone.name)
        control=None
        if kind==5:
            size=L4D2_JIGGLE.size
            model.r.unpack('120s',start)
            payload=_scaled_jiggle(model.data[start:start+size],scale)
        else:
            control_index=model.r.i(start)
            if not 0<=control_index<len(model.bones) or control_index==index:
                raise ValueError('Hueso controlador inválido: '+bone.name)
            control=mapping[model.bones[control_index].name]
            if kind==1:
                model.r.unpack('176s',start)
                axis=model.r.i(start+4)
                if axis not in (0,1,2):raise ValueError('Eje procedural inválido: '+bone.name)
                payload=bytearray(model.data[start:start+176])
                positions=np.array(struct.unpack_from('<18f',payload,8))*scale
                struct.pack_into('<18f',payload,8,*positions)
                values=struct.unpack_from('<42f',payload,8)
            else:
                count,offset=model.r.unpack('ii',start+4)
                if not 0<count<=4096 or offset<12:
                    raise ValueError('Tabla de interpolación inválida: '+bone.name)
                trigger=start+offset
                model.r.table(trigger,count,48,4096)
                payload=bytearray(struct.pack('<iii',control_index,count,12))
                payload.extend(model.data[trigger:trigger+count*48])
                for i in range(count):
                    positions=np.array(struct.unpack_from('<3f',payload,12+i*48+20))*scale
                    struct.pack_into('<3f',payload,12+i*48+20,*positions)
                values=struct.unpack_from('<'+'f'*(count*12),payload,12)
            if not np.isfinite(values).all():raise ValueError('Datos procedurales no finitos: '+bone.name)
            payload=bytes(payload)
        rules.append(Rule(mapping[bone.name],kind,payload,control))
        events.append(dict(event,action='preserved',control=control))
    return rules,events


def restore(data,rules):
    if not rules:return data
    model=Model(lambda name:data,'models/armshub/rules.mdl',geometry=False)
    names={bone.name:i for i,bone in enumerate(model.bones)}
    mutable=bytearray(data);base=model.r.i(160)
    h2=model.r.i(400);linear=h2+model.r.i(h2+16) if h2 and model.r.i(h2+16) else 0
    if linear and model.r.i(linear)!=len(names):raise ValueError('Cache lineal procedural inválida')
    def flags(index,add=0,clear=0):
        offset=base+index*216+160
        value=(struct.unpack_from('<i',mutable,offset)[0]|add)&~clear
        struct.pack_into('<i',mutable,offset,value)
        if linear:struct.pack_into('<i',mutable,linear+model.r.i(linear+4)+index*4,value)
    for rule in rules:
        if rule.bone not in names:raise ValueError('El compilador eliminó el hueso '+rule.bone)
        index=names[rule.bone];bone=base+index*216
        if rule.kind==0:
            struct.pack_into('<ii',mutable,bone+164,0,0);flags(index,clear=4);continue
        payload=bytearray(rule.payload)
        if rule.control is not None:
            if rule.control not in names:raise ValueError('Falta controlador '+rule.control)
            control=names[rule.control]
            struct.pack_into('<i',payload,0,control)
            # The controller must be evaluated even if it has no weighted vertices.
            usage=struct.unpack_from('<i',mutable,bone+160)[0]&0x7ff00
            ancestor=control;visited=set()
            while ancestor>=0:
                if ancestor in visited:raise ValueError('Jerarquía cíclica de control procedural')
                visited.add(ancestor);flags(ancestor,add=usage)
                ancestor=model.bones[ancestor].parent
        mutable.extend(b'\0'*(-len(mutable)%4));start=len(mutable);mutable.extend(payload)
        struct.pack_into('<ii',mutable,bone+164,rule.kind,start-bone);flags(index,add=4)
    struct.pack_into('<i',mutable,76,len(mutable))
    return bytes(mutable)
