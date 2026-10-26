# ArmsHub

Generador de addons de charms para Left 4 Dead 2 con brazos personalizados compartidos y perfiles JSON de Charm Studio, sin una extensión DLL del juego.

Versión 0.3.2. Aplicación para Windows con Python 3.10 o superior y PyQt6.

## Uso

Arrastra los VPK de personajes, armas y charms junto con los perfiles JSON. Asigna los brazos por superviviente, selecciona studiomdl.exe de L4D2 Authoring Tools y genera armshub_charms.vpk.

Los JSON de proyecto restauran las fuentes originales y requieren que sigan disponibles. Un perfil por arma; el programa conserva la geometría del arma en su addon original.

La geometría común de brazos y charms comparte espacio dentro del VPK; esto no garantiza compartir memoria de GPU. Los charms ocultos siguen en los bancos. Se admite LOD 0 y existe un límite de huesos y restricciones en skins/bodygroups.

El addon generado no requiere `-insecure` ni una DLL cargada en el juego. La compatibilidad visual se probó localmente; la validación en servidores remotos sigue pendiente y cada servidor puede restringir addons.

En el modo de huesos «Arreglar», se conservan los procedimientos compatibles; «No arreglar y seguir» omite procedimientos especiales no jiggle.

## Ejecutar desde el código

```powershell
python -m pip install -r requirements.txt
python armshub_main.py
```

El ZIP de Releases incluye el programa portable; extrae la carpeta completa antes de abrir el EXE.
No se distribuyen modelos, texturas, addons de terceros ni configuraciones personales.

## Pruebas

```powershell
python -m unittest discover -s tests -v
```

## Crear el ejecutable

```powershell
python -m pip install -r requirements-dev.txt
python tools/build_release.py
```

El proyecto complementario está en https://github.com/Astolfo-Lock/Charm-Studio.
