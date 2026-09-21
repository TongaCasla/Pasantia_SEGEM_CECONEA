"""
modelos.py - Definición de Signatures DSPy para la extracción de embargos.
"""

import dspy


class ExtraccionEmbargo(dspy.Signature):
    """Extraer información estructurada sobre medidas cautelares y embargos judiciales.

INSTRUCCIONES CRÍTICAS:
- Extraer únicamente la información explícitamente presente en el documento judicial.
- Si un dato no se encuentra en el texto, dejar el campo con cadena vacía "".
- Si hay múltiples personas embargadas, separar los valores con '|' en el mismo orden para: nombre_embargado, dni, cuit_cuil.
- Para 'monto_total', reportar el importe total numérico del embargo (solo números y punto o coma decimal, sin letras ni símbolos '$'). Si no figura explícito un total pero se indica capital y una suma presupuestada para costas/intereses, calcular la suma de ambos importes. Si no se puede determinar o no figura monto, dejar vacío "".
- Para 'monto_contexto', copiar textualmente el fragmento breve del documento donde se ordenan las sumas o el monto de la traba del embargo (ejemplo: '$ 1.200.000 con más la suma de $ 360.000 calculada provisoriamente para intereses y costas').
- Para 'cuenta', extraer el número de cuenta judicial de autos abierta o indicada para el depósito del embargo si está presente.
"""

    documento: str = dspy.InputField(
        desc="Texto del documento judicial o fragmento relevante a analizar"
    )
    nombre_embargado: str = dspy.OutputField(
        desc="Nombre y apellido o razón social de la persona o entidad embargada. Si son varias, separadas por '|'"
    )
    dni: str = dspy.OutputField(
        desc="Número de DNI de cada persona embargada (solo dígitos). Si son varias, separadas por '|' en el mismo orden que nombre_embargado"
    )
    cuit_cuil: str = dspy.OutputField(
        desc="Número de CUIT o CUIL de cada persona embargada (solo dígitos). Si son varias, separadas por '|' en el mismo orden"
    )
    monto_total: str = dspy.OutputField(
        desc="Importe numérico total del embargo (suma de capital + presupuestado para intereses/costas si aplica). Ej: '1560000.00' o '1560000'. Sin signo '$' ni texto"
    )
    monto_contexto: str = dspy.OutputField(
        desc="Fragmento textual exacto del documento donde se expresan los montos (capital, costas, o total)"
    )
    cuenta: str = dspy.OutputField(
        desc="Número de cuenta judicial abierta o asignada para la traba de la medida cautelar"
    )
