# Cambios de ArmsHub

## 0.3.3 experimental — 26 de octubre de 2026

### Bancos separados por charm

- Cada banco contiene unos brazos y un solo charm con su pose y escala. Los
  demás charms ya no se incluyen como geometría oculta ni aportan huesos o
  jiggles inactivos a ese modelo.
- Los perfiles compatibles reutilizan un banco, conservando su propio hueso,
  posición y rotación. Solo se añaden los huesos de destino necesarios para
  los perfiles que utilizan ese banco.
- La salida sigue siendo un único `armshub_charms.vpk`, con reutilización física
  de archivos VVD/VTX idénticos dentro del contenedor.
- El manifiesto y el informe identifican la estrategia `per_charm` y explican
  que no se implementa carga o descarga selectiva de modelos del motor.

### Compatibilidad y uso

- Los perfiles y proyectos JSON anteriores se importan sin conversión. Se
  mantienen el arrastre de VPK, perfiles y proyectos, y la interfaz PyQt6.
- Se conservan los brazos personalizados de los ocho supervivientes, la
  colocación precisa y la corrección de rotaciones próximas a 180°.
- Se mantienen los modos de reparación u omisión de procedimientos especiales,
  el soporte de tipos 1/2/5 y los jiggles en ambos modos.
- Se mantienen LOD 0, el límite de 128 huesos por banco y las restricciones de
  skins y bodygroups. El addon no incorpora modelos o animaciones de las armas:
  sus addons originales deben seguir instalados.
- La interfaz, las instrucciones exportadas y el README indican que hay que
  **reiniciar completamente L4D2 después de habilitar el addon**. Se confirmó
  que los brazos y charms aparecen al reiniciar con el addon habilitado.
- Los JSON externos de proyecto e informe no son necesarios para que el juego
  utilice el VPK.

### Comprobaciones y límites

- 24 pruebas automatizadas del repositorio y comprobación de inicio PyQt6
  correctas; otras ocho pruebas locales de modelos y procedimientos correctas.
- Se generó un proyecto de cinco perfiles y ocho asignaciones en ambos modos:
  40 bancos, 40 modelos, 58–70 huesos por modelo y ningún charm inactivo.
  Se comprobaron colocación, geometría visible y procedimientos activos frente
  a la exportación anterior, sin ampliar las tolerancias de precisión.
- Un candidato con esta organización completó unos tres minutos en Tumtara con
  toda la Workshop sin crash. Falta validar estabilidad prolongada y repetida,
  los ocho supervivientes dentro del juego y servidores remotos.
- No se ha demostrado ahorro de RAM/VRAM ni una mejora exacta de FPS. Separar
  bancos puede aumentar el tamaño del VPK y el tiempo de compilación. En el
  proyecto evaluado, el paquete pasó de unos 111,13 MiB a 134,18 MiB.
- No se requiere una DLL cargada en el juego ni `-insecure`. Los VPK originales
  permanecen intactos. La distribución no incluye mods ni recursos de terceros.

## 0.3.2

Versión publicada anterior: bancos con varios charms por conjunto de brazos,
perfiles y proyectos JSON arrastrables, y archivos de geometría idénticos
compartidos físicamente dentro del VPK.
