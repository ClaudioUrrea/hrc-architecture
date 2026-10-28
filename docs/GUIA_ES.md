# Guía para el autor (resumen en español)

## Qué contiene este repositorio

Una reimplementación completa y compilable de la arquitectura del paper, con todas sus pruebas
pasando:

* **Capa física**: adaptador Universal Robots (RTDE + URScript + Dashboard) escrito
  directamente contra el protocolo público. Incluye un *heartbeat* en el propio controlador:
  el robot se detiene solo si el host deja de enviar. También adaptadores KUKA FRI y ABB EGM, que
  se compilan cuando se aportan el SDK de KUKA o el `egm.proto` de ABB. Por último, un robot
  simulado incorporado y un *mock* para las pruebas.
* **Capa de control**: barrera geométrica, barrera aprendida (entrenamiento propio en NumPy e
  inferencia en C++, local o en un servidor remoto tipo Jetson), monitoreo de velocidad y
  separación ISO/TS 15066 con distancia de frenado físicamente correcta, filtro QP exacto
  (Goldfarb–Idnani) y supervisor con **una sola tabla de prioridades**.
* **Capa de integración**: servidores Modbus TCP y REST propios y OPC-UA (open62541).
* **Inyección de fallas** con llegadas Poisson, agrupadas (Neyman–Scott) o Weibull, más un
  operador simulado.
* **Registro crudo**: un registro binario de 192 bytes por ciclo y eventos en JSONL. Al cerrar,
  el sistema escribe SHA-256 de todos los archivos, deja la carpeta en solo lectura y hace copias
  verificadas a cada respaldo. Es imposible editar un dato sin que el análisis lo detecte.
* **Análisis**: scripts que solo leen corridas crudas verificadas y producen
  `results/results.json`, con la lista de corridas y hashes detrás de cada número. A partir de
  ese archivo, `tools/paper_numbers.py` genera las macros LaTeX del paper. Así el manuscrito no
  puede contener un número que no venga de los datos.
* **Bitácora encadenada** (`tools/worklog.py`, funciona en Windows) para medir el tiempo de
  puesta en marcha de PLC y el esfuerzo de portabilidad. Cualquier edición rompe la cadena.

Lo que **no** contiene: ningún dato y ningún modelo entrenado. Ambos deben salir de tus
corridas.

## Orden recomendado

1. **Hoy**: enviar al editor el correo de transparencia (la versión que elegiste) y publicar
   la nota de `docs/PROVENANCE_NOTICE.md` en Figshare y GitHub. **No publicar** la versión
   v2.1.0 que estaba preparada en `figshare_deposit`.
2. **Día 1–2**: instalar Ubuntu 22.04 con PREEMPT_RT en el PC de control, compilar y correr
   `ctest`. Hacer `git init` (o clonar tu repo) y subir esta versión 3.x a GitHub.
3. **Día 2–3**: corrida piloto (`runs_pilot/`). Ajustar la geometría del escenario, los
   *waypoints* y las ganancias hasta que la celda trabaje razonablemente. Luego **congelar**
   (commit + `git tag campaign-v3`). El piloto nunca entra al paper.
4. **Día 3**: entrenar la barrera (≈1 h) y hacer la conformidad con URSim (≈1 h).
5. **Días 3–18**: campañas en este orden: ablación (12 h), inyección (10 h), sintonía de
   *baselines* (33–67 h), comparación (40 h), sensibilidad (24 h) y temporización (200 h, o
   50 h en el plan reducido). Siempre con dos respaldos (`--backup`).
6. **En paralelo, en Windows**: tres a cinco puestas en marcha de PLC por plataforma,
   cronometradas con `worklog.py`. Idealmente con grabación de pantalla.
7. **Al final**: `python3 analysis/report.py`, luego `tools/paper_numbers.py`. Con eso
   reescribimos el manuscrito.

Tiempo total de máquina: unas 350 h con el plan completo, o unos 5 días con el plan reducido.

## Qué cambia en el paper (resumen)

El detalle está en `docs/DESIGN_DECISIONS.md` y `docs/REVIEWER2_R3_MAP.md`. En resumen:

* El controlador pasa de MPC a un filtro de seguridad CBF-QP de un paso.
* La barrera aprendida pasa a ser una regresión de la holgura.
* Se compara contra tres *baselines* (SSM, campo potencial y CBF geométrica), no seis.
* La prioridad entre modos queda explícita.
* La distancia de frenado se corrige.
* La edad del dato se mide desde la adquisición de la cámara.
* El enlace con el Jetson pasa a ser UDP con su tiempo de transporte medido. No hay código GPU,
  así que el texto sobre memoria *pinned* y unificada se elimina.
* Las tasas de falla son parámetros de diseño, sin fuentes externas.
* Los esfuerzos medidos se describen como «potencialmente optimistas».
* Se corrige la dirección del ratio en el Apéndice C.
* La figura 12a se separa en indicadores independientes.

Los números de la R2 **no se reutilizan**. Lo que digan las nuevas corridas es lo que dirá el
paper, aunque sea peor.
