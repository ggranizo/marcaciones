# Marcaciones biométricas · LEMAS

Aplicación Streamlit basada en los Colab de Mucho Lote 1 y Mucho Lote 2.
Permite subir un Excel, revisar un resumen y descargar un ZIP con un CSV por fecha.

## Ejecutar en un equipo

Requiere Python 3.11 o posterior.

```bash
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows, en lugar de la línea anterior:
# .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Publicar en Streamlit Community Cloud

1. Subir a la raíz de `ggranizo/marcaciones` todos los archivos de este proyecto, incluida la carpeta `.streamlit`.
2. Iniciar sesión en https://share.streamlit.io/ y conectar GitHub.
3. Seleccionar **Create app / New app** y el repositorio `ggranizo/marcaciones`.
4. Elegir la rama que contenga los archivos (por ejemplo, `main`) y `app.py` como archivo principal.
5. En opciones avanzadas, seleccionar Python 3.11 o posterior y desplegar.
6. En **Settings → Sharing**, definir quién puede ver la aplicación. Para uso interno, elegir acceso restringido a personas específicas.

No requiere claves API, base de datos ni credenciales en el código.

## Formatos de entrada

Se lee la primera hoja del Excel (.xlsx o .xls); la primera fila debe contener los encabezados.
Se admiten espacios, mayúsculas y tildes equivalentes en los encabezados.

| Sede | Columnas requeridas | Ejemplo de fecha y hora |
| --- | --- | --- |
| ML1 | ID Empleado, Fecha, Hora | 11/09/2026 y 06:27:13 |
| ML2 | Código, Hora Marca | 2026-09-11 06:27:13 |

La columna Nombre puede existir; no se utiliza en el resultado. ML1 admite horas de Excel como fracción del día.

## Reglas y compatibilidad con los Colab

- Primera marcación por ID y fecha: ingreso.
- Última marcación: salida si hay dos o más registros. Con uno, salida vacía.
- Los duplicados se conservan y cuentan como registros. La interfaz avisa cuando existen.
- Por defecto se completan IDs desde 1 hasta el máximo observado. También se puede elegir desde el mínimo, solo registrados o un rango fijo.
- Los límites de un rango fijo reemplazan el modo seleccionado, igual que en los Colab. Un límite fijo parcial se admite en la función de procesamiento; la interfaz solicita ambos.
- Los IDs sin registro en una fecha se incluyen con horas vacías.
- Solo se generan fechas que contengan marcaciones válidas. No se crean días ausentes del archivo.
- Las filas inválidas se omiten; se muestran sus motivos y pueden descargarse para revisión.
- Una mejora deliberada: se rechazan IDs decimales o infinitos, en vez de truncarlos o provocar errores.
- Si el rango deja IDs fuera, la interfaz avisa. El resumen conserva los conteos de todo el archivo, como los Colab.
- No se calculan horas trabajadas, atrasos, pausas ni jornadas que cruzan medianoche.

Cada CSV contiene exactamente: `ID Empleado`, `Fecha de marcación`, `Hora de ingreso`, `Hora de salida`.
Las fechas usan `DD/MM/AAAA`, las horas `HH:MM:SS`, y los archivos UTF-8 con BOM y separador `;` por defecto.

## Manejo de archivos

Los Excel y resultados se procesan en memoria y el resultado se mantiene en la sesión del usuario.
La aplicación no guarda un historial, no escribe los archivos cargados en disco y no los sube al repositorio.
Cada usuario tiene su propio estado de sesión. El límite de carga es 50 MB; se limita la salida a 100.000 IDs en rangos completos y 2.000.000 de filas.

## Validación

```bash
python -m unittest discover -s tests -v
```

Las ocho pruebas incluidas usan datos sintéticos para verificar las reglas y los errores de entrada.
Además, durante la conversión se compararon los CSV y resúmenes contra los Colab originales en 12 escenarios (dos sedes, tres modos de IDs y dos configuraciones de rango), con coincidencia exacta. La interfaz se verificó con Streamlit AppTest.
Antes de uso operativo, verificar un Excel real de cada sede contra su Colab correspondiente.
