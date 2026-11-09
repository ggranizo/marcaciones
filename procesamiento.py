"""Procesamiento de ML1 y ML2, basado en los Colab originales."""
from dataclasses import dataclass
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile
import re
import unicodedata
import pandas as pd

MAX_IDS = 100_000
MAX_CELDAS_SALIDA = 2_000_000

def normalizar_texto(valor):
    texto = unicodedata.normalize('NFKD', str(valor))
    texto = ''.join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]+', ' ', texto.lower()).strip()

def buscar_columna(columnas, alternativas):
    normalizadas = {normalizar_texto(c): c for c in columnas}
    for alternativa in alternativas:
        if alternativa in normalizadas:
            return normalizadas[alternativa]
    raise ValueError(
        f'No se encontró la columna esperada {alternativas}. '
        f'Columnas disponibles: {list(columnas)}'
    )

def convertir_fecha(valor):
    if pd.isna(valor):
        return pd.NaT
    if hasattr(valor, 'year') and hasattr(valor, 'month') and hasattr(valor, 'day'):
        return pd.Timestamp(valor).normalize()
    texto = str(valor).strip()
    # Protege el formato ISO AAAA-MM-DD para que no se confunda con día/mes.
    if re.match(r'^\d{4}[-/]\d{1,2}[-/]\d{1,2}', texto):
        fecha = pd.to_datetime(texto, errors='coerce', yearfirst=True)
        return fecha.normalize() if pd.notna(fecha) else pd.NaT
    fecha = pd.to_datetime(texto, errors='coerce', dayfirst=True)
    return fecha.normalize() if pd.notna(fecha) else pd.NaT

def convertir_hora(valor):
    if pd.isna(valor):
        return None
    if hasattr(valor, 'hour'):
        return valor.hour * 3600 + valor.minute * 60 + valor.second
    texto = str(valor).strip()
    # También admite valores de hora almacenados por Excel como fracción de un día.
    try:
        numero = float(texto.replace(',', '.'))
        if 0 <= numero < 1:
            return int(round(numero * 86400)) % 86400
    except ValueError:
        pass
    hora = pd.to_datetime(texto, errors='coerce')
    if pd.isna(hora):
        return None
    return hora.hour * 3600 + hora.minute * 60 + hora.second

def formatear_hora(segundos):
    if pd.isna(segundos):
        return ''
    segundos = int(segundos)
    return f'{segundos // 3600:02d}:{(segundos % 3600) // 60:02d}:{segundos % 60:02d}'


def convertir_fecha_hora(valor):
    if pd.isna(valor):
        return pd.NaT
    # Los valores AAAA-MM-DD se interpretan explícitamente como año-mes-día.
    texto = str(valor).strip()
    if re.match(r'^\d{4}[-/]\d{1,2}[-/]\d{1,2}', texto):
        return pd.to_datetime(texto, errors='coerce', yearfirst=True)
    return pd.to_datetime(texto, errors='coerce', dayfirst=True)



@dataclass
class Resultado:
    resumen: pd.DataFrame
    invalidas: pd.DataFrame
    csv_por_fecha: dict[str, bytes]
    zip_bytes: bytes
    validas: int
    ids: list[int]
    fuera_rango: int
    duplicadas: int


def procesar_excel(contenido: bytes, sede: str, modo_ids: str = 'desde_1',
                   id_inicial: int | None = None, id_final: int | None = None,
                   separador: str = ';') -> Resultado:
    if sede not in ('ML1', 'ML2'):
        raise ValueError('Seleccione ML1 o ML2.')
    if modo_ids not in ('desde_1', 'desde_minimo', 'solo_registrados'):
        raise ValueError('Modo de IDs no reconocido.')
    if separador not in (';', ',', '\t'):
        raise ValueError('Separador no admitido.')
    for limite in (id_inicial, id_final):
        if limite is not None and (isinstance(limite, bool) or int(limite) != limite):
            raise ValueError('Los límites de ID deben ser números enteros.')
    df = pd.read_excel(BytesIO(contenido), sheet_name=0)
    df.columns = [str(c).strip() for c in df.columns]
    if df.empty:
        raise ValueError('El Excel no contiene filas de marcaciones.')
    col_id = buscar_columna(df.columns, ['id empleado', 'id de empleado', 'idempleado']
                           if sede == 'ML1' else ['codigo', 'id empleado', 'id de empleado'])
    ids = pd.to_numeric(df[col_id], errors='coerce')
    # Evita convertir un ID decimal en otro empleado por truncamiento.
    ids_validos = ids.notna() & ids.ne(float('inf')) & ids.ne(float('-inf'))
    ids_validos &= ids.mod(1).eq(0)
    datos = pd.DataFrame({'ID Empleado': ids})
    if sede == 'ML1':
        col_fecha = buscar_columna(df.columns, ['fecha', 'fecha marcacion', 'fecha de marcacion'])
        col_hora = buscar_columna(df.columns, ['hora', 'hora marcacion', 'hora de marcacion'])
        datos['Fecha'] = df[col_fecha].apply(convertir_fecha)
        datos['Hora segundos'] = df[col_hora].apply(convertir_hora)
    else:
        col_marca = buscar_columna(df.columns, ['hora marca', 'hora de marca', 'fecha hora', 'fecha y hora', 'marcacion'])
        fecha_hora = df[col_marca].apply(convertir_fecha_hora)
        datos['Fecha'] = fecha_hora.dt.normalize()
        datos['Hora segundos'] = fecha_hora.dt.hour * 3600 + fecha_hora.dt.minute * 60 + fecha_hora.dt.second
    errores = pd.DataFrame(index=df.index)
    errores['ID inválido'] = ~ids_validos
    errores['Fecha inválida'] = datos['Fecha'].isna()
    errores['Hora inválida'] = datos['Hora segundos'].isna()
    invalidas_mask = errores.any(axis=1)
    invalidas = df.loc[invalidas_mask].copy()
    invalidas.insert(0, 'Fila Excel (incluye encabezado)', df.index[invalidas_mask] + 2)
    invalidas.insert(1, 'Motivo', [
        ', '.join(fila.index[fila]) for _, fila in errores.loc[invalidas_mask].iterrows()
    ])
    datos = datos.loc[~invalidas_mask].copy()
    if datos.empty:
        raise ValueError('No quedaron marcaciones válidas después de revisar ID, fecha y hora.')
    datos['ID Empleado'] = datos['ID Empleado'].astype('int64')
    datos['Hora segundos'] = datos['Hora segundos'].astype(int)
    observados = sorted(int(x) for x in datos['ID Empleado'].unique())
    inicio = int(id_inicial) if id_inicial is not None else (1 if modo_ids == 'desde_1' else min(observados))
    fin = int(id_final) if id_final is not None else max(observados)
    if inicio > fin:
        raise ValueError('El ID inicial no puede ser mayor que el ID final.')
    if modo_ids == 'solo_registrados' and id_inicial is None and id_final is None:
        ids_salida = observados
    else:
        if fin - inicio + 1 > MAX_IDS:
            raise ValueError('El rango supera 100.000 IDs. Use «Solo IDs registrados» o reduzca el rango.')
        ids_salida = list(range(inicio, fin + 1))
    fechas = sorted(datos['Fecha'].unique())
    if len(ids_salida) * len(fechas) > MAX_CELDAS_SALIDA:
        raise ValueError('La salida supera 2.000.000 de filas. Reduzca el rango de IDs o divida el archivo por períodos.')
    fuera_rango = int((~datos['ID Empleado'].isin(ids_salida)).sum())
    duplicadas = int(datos.duplicated(['ID Empleado', 'Fecha', 'Hora segundos']).sum())
    csv_por_fecha, resumen = {}, []
    for fecha in fechas:
        fecha = pd.Timestamp(fecha)
        dia = datos.loc[datos['Fecha'].eq(fecha)]
        agrupado = dia.groupby('ID Empleado')['Hora segundos'].agg(Primera='min', Ultima='max', Marcaciones='size')
        salida = pd.DataFrame({'ID Empleado': ids_salida}).join(agrupado, on='ID Empleado')
        salida['Fecha de marcación'] = fecha.strftime('%d/%m/%Y')
        salida['Hora de ingreso'] = salida['Primera'].apply(formatear_hora)
        salida['Hora de salida'] = salida['Ultima'].where(salida['Marcaciones'].ge(2)).apply(formatear_hora)
        salida = salida[['ID Empleado', 'Fecha de marcación', 'Hora de ingreso', 'Hora de salida']]
        nombre = f'marcaciones_{fecha:%Y-%m-%d}.csv'
        csv_por_fecha[nombre] = salida.to_csv(index=False, sep=separador).encode('utf-8-sig')
        resumen.append({
            'Fecha': fecha.strftime('%d/%m/%Y'),
            'Empleados con marcación': int(dia['ID Empleado'].nunique()),
            'Con una sola marcación': int(agrupado['Marcaciones'].eq(1).sum()),
            'Con dos o más marcaciones': int(agrupado['Marcaciones'].ge(2).sum()),
            'Filas generadas': len(salida),
        })
    buffer = BytesIO()
    with ZipFile(buffer, 'w', compression=ZIP_DEFLATED) as archivo_zip:
        for nombre, contenido_csv in csv_por_fecha.items():
            archivo_zip.writestr(nombre, contenido_csv)
    return Resultado(pd.DataFrame(resumen), invalidas, csv_por_fecha, buffer.getvalue(),
                     len(datos), ids_salida, fuera_rango, duplicadas)
