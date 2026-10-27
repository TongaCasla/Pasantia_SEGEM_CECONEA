import os
import unittest

from extraccion_fragmento import ExtraccionFragmento, ExtractorConfig, ResultadoExtraccion

PALABRAS = {
    "Datos_Embargado": ["dni", "cuit"],
    "Montos": ["hasta cubrir la suma"],
}

TEXTO = (
    "Decrétase embargo sobre Juan Pérez, D.N.I. 20.123.456, CUIT 20-20123456-7, "
    "hasta cubrir la suma de $ 150.000. Firmado: Dr. Gómez, Juez. "
    "El titular del DNI deberá presentarse."
)


class ExtraccionFragmentoTest(unittest.TestCase):

    def test_extrae_en_memoria_y_devuelve_resultado_tipado(self):
        extractor = ExtraccionFragmento(PALABRAS, ExtractorConfig(chars_antes=20, chars_despues=20))
        res = extractor.extraer(TEXTO)
        self.assertIsInstance(res, ResultadoExtraccion)
        self.assertTrue(res.tiene_coincidencias)
        for f in res.fragmentos_principales:
            self.assertEqual(TEXTO[f.inicio_fragmento:f.fin_fragmento], f.fragmento)
        self.assertEqual(res.categorias_faltantes, [])

    def test_normaliza_tildes_y_puntos(self):
        extractor = ExtraccionFragmento({"X": ["dni"]}, ExtractorConfig(habilitar_reduccion=False))
        res = extractor.extraer("Documento D.N.I. 123")
        self.assertEqual(len(res.fragmentos_principales), 1)

    def test_reduccion_habilitada_separa_dni_sin_numero(self):
        extractor = ExtraccionFragmento(PALABRAS, ExtractorConfig(chars_antes=10, chars_despues=15,
                                                                  habilitar_agrupacion=False))
        res = extractor.extraer(TEXTO)
        motivos = [f.palabra_reduccion for f in res.fragmentos_reducidos]
        self.assertIn("sin_numero", motivos)

    def test_reduccion_por_patrones(self):
        extractor = ExtraccionFragmento(PALABRAS, ExtractorConfig(chars_antes=10, chars_despues=200,
                                                                  habilitar_agrupacion=False),
                                        palabras_reduccion=["juez"])
        res = extractor.extraer(TEXTO)
        self.assertIn("juez", [f.palabra_reduccion for f in res.fragmentos_reducidos])

    def test_reduccion_deshabilitada_no_reduce_nada(self):
        extractor = ExtraccionFragmento(PALABRAS, ExtractorConfig(habilitar_reduccion=False),
                                        palabras_reduccion=["juez"])
        res = extractor.extraer(TEXTO)
        self.assertEqual(res.fragmentos_reducidos, [])

    def test_agrupacion_fusiona_superpuestos_de_misma_categoria(self):
        cfg_on = ExtractorConfig(chars_antes=50, chars_despues=50, habilitar_reduccion=False)
        cfg_off = ExtractorConfig(chars_antes=50, chars_despues=50, habilitar_reduccion=False,
                                  habilitar_agrupacion=False)
        agrupado = ExtraccionFragmento(PALABRAS, cfg_on).extraer(TEXTO).fragmentos_principales
        individual = ExtraccionFragmento(PALABRAS, cfg_off).extraer(TEXTO).fragmentos_principales
        self.assertLess(len(agrupado), len(individual))
        self.assertTrue(any(" | " in f.palabra_clave for f in agrupado))

    def test_categoria_cero_cero_se_omite(self):
        cfg = ExtractorConfig(chars_por_categoria={"Montos": (0, 0)}, habilitar_reduccion=False)
        res = ExtraccionFragmento(PALABRAS, cfg).extraer(TEXTO)
        self.assertNotIn("Montos", res.categorias_encontradas)
        self.assertIn("Montos", res.categorias_faltantes)

    def test_texto_vacio(self):
        res = ExtraccionFragmento(PALABRAS).extraer("")
        self.assertFalse(res.tiene_coincidencias)
        self.assertEqual(res.categorias_faltantes, ["Datos_Embargado", "Montos"])

    def test_config_invalida(self):
        with self.assertRaises(ValueError):
            ExtractorConfig(chars_antes=-1)
        with self.assertRaises(ValueError):
            ExtraccionFragmento([])

    def test_contexto(self):
        extractor = ExtraccionFragmento(PALABRAS, palabras_clave_contexto=["embargo sobre"])
        res = extractor.extraer(TEXTO)
        self.assertIn("embargo sobre", res.contexto_embargado)
        self.assertEqual(res.palabras_clave_contexto, "embargo sobre")

    def test_extraer_lote(self):
        extractor = ExtraccionFragmento(PALABRAS)
        resultados = list(extractor.extraer_lote([TEXTO, "", None]))
        self.assertEqual(len(resultados), 3)

    def test_cuil_sin_numero_se_reduce(self):
        extractor = ExtraccionFragmento(
            {"Datos_Embargado": ["cuil"]},
            ExtractorConfig(chars_antes=10, chars_despues=30, habilitar_agrupacion=False)
        )
        res = extractor.extraer("El titular con CUIL sin datos numericos presentes.")
        self.assertEqual(len(res.fragmentos_reducidos), 1)
        self.assertEqual(res.fragmentos_reducidos[0].palabra_reduccion, "sin_numero")

    def test_reduccion_con_puntos_dr_y_dra(self):
        extractor = ExtraccionFragmento(
            {"Datos_Embargado": ["dni"]},
            ExtractorConfig(chars_antes=10, chars_despues=50, habilitar_agrupacion=False),
            palabras_reduccion=["dr.", "dra."]
        )
        res = extractor.extraer("DNI 20123456 con intervencion de Dr. Gomez juez.")
        self.assertEqual(len(res.fragmentos_reducidos), 1)
        self.assertIn(res.fragmentos_reducidos[0].palabra_reduccion, ["dr.", "dr", "dra.", "dra"])

    def test_generar_carpeta_ejecucion_evita_colisiones(self):
        import tempfile
        from extraccion_fragmento.cli import generar_carpeta_ejecucion
        with tempfile.TemporaryDirectory() as tmpdir:
            c1 = generar_carpeta_ejecucion(tmpdir)
            c2 = generar_carpeta_ejecucion(tmpdir)
            self.assertNotEqual(c1, c2)
            self.assertTrue(os.path.exists(c1))
            self.assertTrue(os.path.exists(c2))


if __name__ == "__main__":
    unittest.main()
