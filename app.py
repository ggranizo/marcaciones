"""Interfaz Streamlit para los biométricos ML1 y ML2."""
from io import BytesIO
import logging

import pandas as pd
import streamlit as st

from procesamiento import procesar_excel

st.set_page_config(page_title='Marcaciones · LEMAS', page_icon='🕒', layout='wide')
st.title('Marcaciones biométricas')
st.caption('LEMAS · Mucho Lote 1 y Mucho Lote 2')
st.write('Carga el Excel del biométrico y descarga un CSV por fecha, con la primera y la última marcación de cada empleado.')

with st.sidebar:
    st.header('Configuración')
    sede = st.selectbox('Sede / formato del biométrico', ['ML1', 'ML2'])
    etiquetas = {
        'Desde 1 hasta el ID máximo': 'desde_1',
        'Desde el ID mínimo hasta el máximo': 'desde_minimo',
        'Solo IDs registrados en el archivo': 'solo_registrados',
    }
    etiqueta_modo = st.selectbox('Empleados en la salida', list(etiquetas))
    rango_fijo = st.checkbox('Definir rango fijo de IDs', help='El rango fijo reemplaza el modo anterior, igual que en los Colab.')
    inicial = final = None
    if rango_fijo:
        inicial = st.number_input('ID inicial', value=1, step=1)
        final = st.number_input('ID final', value=130 if sede == 'ML1' else 80, step=1)
    separadores = {'Punto y coma (;)': ';', 'Coma (,)': ',', 'Tabulación': '\t'}
    etiqueta_sep = st.selectbox('Separador del CSV', list(separadores))
    st.caption('El separador predeterminado es punto y coma. Los CSV usan UTF-8 con BOM.')

st.info('ML1: ID Empleado, Fecha y Hora.' if sede == 'ML1' else 'ML2: Código y Hora Marca (fecha y hora en una misma columna).')
archivo = st.file_uploader('Archivo Excel del biométrico', type=['xlsx', 'xls'],
                           help='Se procesa la primera hoja. Los nombres de empleados no se incluyen en los CSV de salida.')
st.caption('Los archivos se procesan en memoria. Esta aplicación no crea un historial ni guarda archivos en el repositorio.')

# Streamlit mantiene el resultado exclusivamente en la sesión de este usuario.
config = (sede, etiquetas[etiqueta_modo], inicial, final, separadores[etiqueta_sep])
if archivo is None:
    st.session_state.pop('procesamiento', None)
else:
    contenido = archivo.getvalue()
    # Comparar los bytes evita reutilizar un resultado de otro archivo con el mismo nombre.
    identidad = (contenido, config)
    previo = st.session_state.get('procesamiento')
    if previo is not None and previo['identidad'] != identidad:
        st.session_state.pop('procesamiento', None)
    if st.button('Procesar marcaciones', type='primary'):
        st.session_state.pop('procesamiento', None)
        try:
            with st.spinner('Procesando marcaciones…'):
                resultado = procesar_excel(contenido, *config)
            st.session_state['procesamiento'] = {'identidad': identidad, 'resultado': resultado}
        except (ValueError, TypeError, OverflowError) as exc:
            st.error(str(exc))
        except Exception:
            logging.exception('No se pudo procesar el Excel')
            st.error('No se pudo leer el archivo. Comprueba que sea un Excel válido, que la primera hoja contenga los encabezados y que corresponda a la sede seleccionada.')

previo = st.session_state.get('procesamiento')
if previo is not None:
    resultado = previo['resultado']
    st.success('Procesamiento completado. El ZIP está listo para descargar.')
    c1, c2, c3, c4 = st.columns(4)
    c1.metric('Marcaciones válidas', f'{resultado.validas:,}')
    c2.metric('Filas inválidas omitidas', f'{len(resultado.invalidas):,}')
    c3.metric('Fechas procesadas', len(resultado.resumen))
    c4.metric('IDs por fecha', f'{len(resultado.ids):,}')
    st.caption(f'IDs incluidos: {min(resultado.ids)} a {max(resultado.ids)}. El modo «Solo IDs registrados» puede contener saltos en la secuencia.')
    if resultado.fuera_rango:
        st.warning(f'{resultado.fuera_rango:,} marcaciones válidas corresponden a IDs fuera del rango de salida. Revisa el rango antes de usar los CSV. El resumen cuenta todas las marcaciones válidas del archivo.')
    if resultado.duplicadas:
        st.warning(f'Se detectaron {resultado.duplicadas:,} registros repetidos del mismo ID, fecha y hora. Se conservan y cuentan como marcaciones, igual que en los Colab; dos registros idénticos generan ingreso y salida iguales.')
    st.download_button('Descargar todos los CSV (ZIP)', data=resultado.zip_bytes,
                       file_name=f'CSV_Marcaciones_{sede}.zip', mime='application/zip', type='primary')
    st.subheader('Resumen por fecha')
    st.dataframe(resultado.resumen, hide_index=True, width='stretch')
    with st.expander('Vista previa y descarga de una fecha'):
        nombre_csv = st.selectbox('CSV del día', list(resultado.csv_por_fecha))
        csv_bytes = resultado.csv_por_fecha[nombre_csv]
        vista = pd.read_csv(BytesIO(csv_bytes), sep=separadores[etiqueta_sep], keep_default_na=False)
        st.dataframe(vista.head(200), hide_index=True, width='stretch')
        if len(vista) > 200:
            st.caption('Vista previa limitada a 200 filas. La descarga contiene todas las filas.')
        st.download_button('Descargar CSV de esta fecha', data=csv_bytes, file_name=nombre_csv, mime='text/csv')
    if not resultado.invalidas.empty:
        with st.expander('Filas inválidas omitidas y motivos'):
            st.dataframe(resultado.invalidas.head(200), hide_index=True, width='stretch')
            st.download_button('Descargar filas inválidas',
                               data=resultado.invalidas.to_csv(index=False, sep=';').encode('utf-8-sig'),
                               file_name=f'Filas_invalidas_{sede}.csv', mime='text/csv')

with st.expander('Reglas de procesamiento'):
    st.markdown('''
- La primera marcación del día se registra como ingreso.
- La última se registra como salida cuando existen dos o más registros.
- Con una sola marcación, la salida queda vacía.
- Los IDs incluidos sin marcaciones en esa fecha aparecen con las horas vacías.
- Se genera un CSV solo para las fechas con al menos una marcación válida en el archivo.
- Se conserva el orden de columnas: ID Empleado, Fecha de marcación, Hora de ingreso y Hora de salida.
- Las fechas se presentan como DD/MM/AAAA y las horas como HH:MM:SS.
- No se calculan atrasos, jornadas, horas trabajadas ni pares intermedios de marcaciones.
''')
