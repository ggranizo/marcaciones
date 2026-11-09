from io import BytesIO
from zipfile import ZipFile
import unittest
import pandas as pd
from procesamiento import procesar_excel


def excel(datos):
    buffer = BytesIO()
    pd.DataFrame(datos).to_excel(buffer, index=False)
    return buffer.getvalue()


def leer(resultado, fecha='2026-09-11', sep=';'):
    return pd.read_csv(BytesIO(resultado.csv_por_fecha[f'marcaciones_{fecha}.csv']),
                       sep=sep, keep_default_na=False)


class ProcesamientoTest(unittest.TestCase):
    def test_ml1_ingreso_salida_una_y_ausentes(self):
        r = procesar_excel(excel({'ID Empleado': [3, 1, 3, 3],
            'Fecha': ['11/09/2026'] * 4, 'Hora': ['17:20:00', '08:00:00', '06:30:00', '12:00:00']}), 'ML1')
        d = leer(r)
        self.assertEqual(list(d.columns), ['ID Empleado', 'Fecha de marcación', 'Hora de ingreso', 'Hora de salida'])
        self.assertEqual(d.iloc[0].tolist(), [1, '11/09/2026', '08:00:00', ''])
        self.assertEqual(d.iloc[1].tolist(), [2, '11/09/2026', '', ''])
        self.assertEqual(d.iloc[2].tolist(), [3, '11/09/2026', '06:30:00', '17:20:00'])

    def test_ml2_fechas_iso_sin_dias_inventados(self):
        r = procesar_excel(excel({'Código': [2, 2, 5], 'Hora Marca': [
            '2026-09-11 06:27:13', '2026-09-11 17:00:00', '2026-09-13 08:00:00']}), 'ML2')
        self.assertEqual(list(r.csv_por_fecha), ['marcaciones_2026-09-11.csv', 'marcaciones_2026-09-13.csv'])
        self.assertEqual(leer(r).iloc[1]['Hora de ingreso'], '06:27:13')
        self.assertEqual(leer(r).iloc[1]['Hora de salida'], '17:00:00')
        with ZipFile(BytesIO(r.zip_bytes)) as z:
            self.assertEqual(z.namelist(), list(r.csv_por_fecha))
            self.assertTrue(z.read(z.namelist()[0]).startswith(b'\xef\xbb\xbf'))

    def test_modos_y_limites(self):
        b = excel({'Código': [3, 5], 'Hora Marca': ['2026-09-11 08:00:00'] * 2})
        self.assertEqual(procesar_excel(b, 'ML2', 'desde_minimo').ids, [3, 4, 5])
        self.assertEqual(procesar_excel(b, 'ML2', 'solo_registrados').ids, [3, 5])
        r = procesar_excel(b, 'ML2', 'solo_registrados', 1, 3)
        self.assertEqual(r.ids, [1, 2, 3])
        self.assertEqual(r.fuera_rango, 1)
        with self.assertRaisesRegex(ValueError, 'mayor'):
            procesar_excel(b, 'ML2', id_inicial=8, id_final=3)

    def test_invalidas_no_trunca_ids(self):
        r = procesar_excel(excel({'ID Empleado': [1, 2.5, 3, 4, 5],
            'Fecha': ['11/09/2026', '11/09/2026', '2026-99-11', '11/09/2026', '11/09/2026'],
            'Hora': ['08:00:00', '08:00:00', '08:00:00', 'xxx', '09:00:00']}), 'ML1')
        self.assertEqual(r.validas, 2)
        self.assertEqual(len(r.invalidas), 3)
        self.assertEqual(r.invalidas.iloc[0, 0], 3)
        self.assertIn('ID inválido', r.invalidas.iloc[0, 1])

    def test_duplicadas_se_conservan(self):
        r = procesar_excel(excel({'Código': [1, 1], 'Hora Marca': ['2026-09-11 08:00:00'] * 2}), 'ML2')
        self.assertEqual(r.duplicadas, 1)
        self.assertEqual(leer(r).iloc[0]['Hora de salida'], '08:00:00')

    def test_horas_excel_y_separador(self):
        r = procesar_excel(excel({'ID Empleado': [1, 1], 'Fecha': ['2026-09-11'] * 2,
                                'Hora': [0.25, 0.75]}), 'ML1', separador=',')
        d = leer(r, sep=',')
        self.assertEqual(d.iloc[0]['Hora de ingreso'], '06:00:00')
        self.assertEqual(d.iloc[0]['Hora de salida'], '18:00:00')

    def test_errores_claros(self):
        with self.assertRaisesRegex(ValueError, 'columna esperada'):
            procesar_excel(excel({'Campo': [1]}), 'ML1')
        with self.assertRaisesRegex(ValueError, 'no contiene filas'):
            procesar_excel(excel({'Código': [], 'Hora Marca': []}), 'ML2')
        with self.assertRaisesRegex(ValueError, 'No quedaron'):
            procesar_excel(excel({'Código': [None], 'Hora Marca': ['mal']}), 'ML2')
        with self.assertRaisesRegex(ValueError, '100.000'):
            procesar_excel(excel({'Código': [200000], 'Hora Marca': ['2026-09-11 08:00:00']}), 'ML2')

    def test_resultados_independientes(self):
        a = procesar_excel(excel({'Código': [1], 'Hora Marca': ['2026-09-11 08:00:00']}), 'ML2')
        antes = a.zip_bytes
        b = procesar_excel(excel({'Código': [9], 'Hora Marca': ['2026-09-13 09:00:00']}), 'ML2')
        self.assertEqual(a.zip_bytes, antes)
        self.assertNotEqual(a.zip_bytes, b.zip_bytes)


if __name__ == '__main__':
    unittest.main()
