# ArmsHub

Generador de addons de charms para Left 4 Dead 2 con brazos personalizados compartidos y perfiles JSON de Charm Studio, sin una extensión DLL del juego.

Versión 0.3.3 experimental. Aplicación para Windows con Python 3.10 o superior y PyQt6.

Descarga el [portable de Windows 0.3.3](https://github.com/Astolfo-Lock/ArmsHub/releases/tag/v0.3.3).
Los cambios de esta versión están en [CHANGELOG.md](CHANGELOG.md).

## Uso

Arrastra los VPK de personajes, armas y charms junto con los perfiles JSON. Asigna los brazos por superviviente, selecciona studiomdl.exe de L4D2 Authoring Tools y genera armshub_charms.vpk.

Los JSON de proyecto restauran las fuentes originales y requieren que sigan disponibles. Un perfil por arma; el programa conserva la geometría del arma en su addon original.

Después de copiar el VPK a `left4dead2/addons`, habilítalo en el menú de complementos, cierra L4D2 por completo y vuelve a iniciarlo desde Steam. Activarlo con el juego abierto puede dejar vigentes los datos de armas de esa sesión; volver al menú o cambiar de mapa puede no bastar. Se confirmó la aparición de brazos y charms después de reiniciar con el addon habilitado.

Los archivos `armshub_project.json` y `armshub_report.json` son para ArmsHub y para consultar la exportación. No hace falta copiarlos a la carpeta de addons: L4D2 usa los scripts y modelos contenidos en el VPK.

Cada banco contiene los brazos seleccionados y un solo charm con su pose y escala. Los perfiles compatibles reutilizan ese banco y conservan su propio hueso, posición y rotación. No se incorporan los demás charms como geometría oculta. Los proyectos y perfiles anteriores se pueden importar sin convertirlos; al regenerar se usa esta organización automáticamente.

Los archivos idénticos siguen compartiendo espacio dentro del único VPK. Esto no garantiza ahorro de RAM/VRAM ni controla la carga o descarga de modelos del motor. Puede aumentar el tamaño del paquete y el tiempo de compilación frente a los bancos con todos los charms. Se admite LOD 0, un máximo de 128 huesos por banco y se mantienen las restricciones en skins/bodygroups.

Una prueba local del candidato con toda la Workshop y Tumtara superó tres minutos sin crash; el banco anterior falló durante la observación. Faltan pruebas prolongadas, repetidas y de los ocho supervivientes. No se certifica estabilidad ni ahorro de memoria por compilar.

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
