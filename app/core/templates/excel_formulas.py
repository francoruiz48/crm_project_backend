from typing import Dict
from dataclasses import dataclass

@dataclass
class ExcelFormula:
    name_spanish: str
    name_english: str
    description: str
    example: str
    category: str
    note: str = ""

EXCEL_FORMULAS: Dict[str, ExcelFormula] = {
    # =========================================================================
    # LÓGICA
    # =========================================================================
    "IF": ExcelFormula(
        name_spanish="SI",
        name_english="IF",
        description="Evalúa una condición. Si es verdadera devuelve el primer valor, si no, el segundo.",
        example='IF(Edad >= 18, "Mayor", "Menor")',
        category="Lógica",
        note="Puedes anidar varios IF dentro de otros."
    ),
    "AND": ExcelFormula(
        name_spanish="Y",
        name_english="AND",
        description="Devuelve VERDADERO si todos los argumentos son verdaderos.",
        example="AND(Edad > 18, Tiene_Licencia = TRUE)",
        category="Lógica",
        note="Separa las condiciones con comas."
    ),
    "OR": ExcelFormula(
        name_spanish="O",
        name_english="OR",
        description="Devuelve VERDADERO si al menos uno de los argumentos es verdadero.",
        example="OR(Es_VIP = TRUE, Compra_Total > 10000)",
        category="Lógica"
    ),
    "NOT": ExcelFormula(
        name_spanish="NO",
        name_english="NOT",
        description="Invierte el valor lógico (Verdadero -> Falso).",
        example="NOT(Es_Cliente_Activo)",
        category="Lógica"
    ),

    # =========================================================================
    # TEXTO - BÁSICO
    # =========================================================================
    "CONCAT": ExcelFormula(
        name_spanish="CONCAT",
        name_english="CONCAT",
        description="Une dos o más cadenas de texto.",
        example='CONCAT(Nombre, " ", Apellido)',
        category="Texto",
        note="Ignora valores vacíos automáticamente."
    ),
    "LEN": ExcelFormula(
        name_spanish="LARGO",
        name_english="LEN",
        description="Devuelve la cantidad de caracteres de un texto.",
        example="LEN(DNI)",
        category="Texto"
    ),
    "LOWER": ExcelFormula(
        name_spanish="MINUSCULA",
        name_english="LOWER",
        description="Convierte todo el texto a minúsculas.",
        example="LOWER(Email)",
        category="Texto"
    ),
    "UPPER": ExcelFormula(
        name_spanish="MAYUSCULA",
        name_english="UPPER",
        description="Convierte todo el texto a mayúsculas.",
        example="UPPER(Apellido)",
        category="Texto"
    ),
    "PROPER": ExcelFormula(
        name_spanish="NOMPROPIO",
        name_english="PROPER",
        description="Pone en mayúscula la primera letra de cada palabra.",
        example='PROPER("juan perez") -> "Juan Perez"',
        category="Texto"
    ),

    # =========================================================================
    # TEXTO - LIMPIEZA Y EXTRACCIÓN
    # =========================================================================
    "TRIM": ExcelFormula(
        name_spanish="ESPACIOS",
        name_english="TRIM",
        description="Elimina espacios vacíos al principio y al final del texto.",
        example="TRIM(Nombre)",
        category="Texto",
        note="Ideal para limpiar datos copiados de otras webs."
    ),
    "SUBSTITUTE": ExcelFormula(
        name_spanish="SUSTITUIR",
        name_english="SUBSTITUTE",
        description="Reemplaza un texto específico por otro.",
        example='SUBSTITUTE(Telefono, "-", "")',
        category="Texto",
        note="Distingue entre mayúsculas y minúsculas."
    ),
    "FIND": ExcelFormula(
        name_spanish="ENCONTRAR",
        name_english="FIND",
        description="Devuelve la posición donde empieza un texto dentro de otro.",
        example='FIND("@", Email)',
        category="Texto",
        note="Devuelve 0 si no encuentra el texto (a diferencia de Excel que da error)."
    ),
    "LEFT": ExcelFormula(
        name_spanish="IZQUIERDA",
        name_english="LEFT",
        description="Extrae los primeros X caracteres de un texto.",
        example="LEFT(Codigo_Postal, 4)",
        category="Texto"
    ),
    "RIGHT": ExcelFormula(
        name_spanish="DERECHA",
        name_english="RIGHT",
        description="Extrae los últimos X caracteres de un texto.",
        example="RIGHT(Telefono, 4)",
        category="Texto"
    ),
    "MID": ExcelFormula(
        name_spanish="EXTRAE",
        name_english="MID",
        description="Extrae caracteres desde una posición inicial.",
        example="MID(Patente, 1, 3)",
        category="Texto",
        note="La posición inicial es 1 (no 0)."
    ),
    "REGEXMATCH": ExcelFormula(
        name_spanish="REGEX",
        name_english="REGEXMATCH",
        description="Devuelve VERDADERO si el texto cumple con el patrón (Expresión Regular).",
        example='REGEXMATCH(Email, "^[a-z0-9]+@")',
        category="Texto",
        note="IMPORTANTE: El patrón debe estar siempre entre comillas dobles (\")."
    ),

    # =========================================================================
    # MATEMÁTICAS
    # =========================================================================
    "SUM": ExcelFormula(
        name_spanish="SUMA",
        name_english="SUM",
        description="Suma una lista de números.",
        example="SUM(Subtotal, Impuestos, Envio)",
        category="Matemáticas",
        note="Ignora textos o valores vacíos."
    ),
    "AVERAGE": ExcelFormula(
        name_spanish="PROMEDIO",
        name_english="AVERAGE",
        description="Calcula el promedio aritmético.",
        example="AVERAGE(Nota_1, Nota_2, Nota_3)",
        category="Matemáticas"
    ),
    "MAX": ExcelFormula(
        name_spanish="MAX",
        name_english="MAX",
        description="Devuelve el valor más alto de la lista.",
        example="MAX(Oferta_1, Oferta_2)",
        category="Matemáticas"
    ),
    "MIN": ExcelFormula(
        name_spanish="MIN",
        name_english="MIN",
        description="Devuelve el valor más bajo de la lista.",
        example="MIN(Precio_Lista, Precio_Promo)",
        category="Matemáticas"
    ),
    "ROUND": ExcelFormula(
        name_spanish="REDONDEAR",
        name_english="ROUND",
        description="Redondea un número a una cantidad de decimales.",
        example="ROUND(Total_Calculado, 2)",
        category="Matemáticas",
        note="Si omites los decimales, redondea al entero más cercano."
    ),
    "INT": ExcelFormula(
        name_spanish="ENTERO",
        name_english="INT",
        description="Devuelve solo la parte entera de un número.",
        example="INT(4.9) -> 4",
        category="Matemáticas"
    ),
    "MOD": ExcelFormula(
        name_spanish="RESIDUO",
        name_english="MOD",
        description="Devuelve el resto de la división.",
        example="MOD(Cantidad, 2)",
        category="Matemáticas",
        note="Útil para saber si un número es par (resultado 0) o impar (resultado 1)."
    ),
    "ABS": ExcelFormula(
        name_spanish="ABS",
        name_english="ABS",
        description="Valor absoluto (convierte negativos a positivos).",
        example="ABS(Saldo_Pendiente)",
        category="Matemáticas"
    ),

    # =========================================================================
    # FECHA Y HORA
    # =========================================================================
    "TODAY": ExcelFormula(
        name_spanish="HOY",
        name_english="TODAY",
        description="Devuelve la fecha actual (sin hora).",
        example="TODAY()",
        category="Fecha",
        note="No requiere argumentos dentro de los paréntesis."
    ),
    "NOW": ExcelFormula(
        name_spanish="AHORA",
        name_english="NOW",
        description="Devuelve la fecha y hora actual.",
        example="NOW()",
        category="Fecha"
    ),
    "YEAR": ExcelFormula(
        name_spanish="AÑO",
        name_english="YEAR",
        description="Extrae el año de una fecha.",
        example="YEAR(Fecha_Nacimiento)",
        category="Fecha"
    ),
    "MONTH": ExcelFormula(
        name_spanish="MES",
        name_english="MONTH",
        description="Extrae el mes de una fecha (1-12).",
        example="MONTH(TODAY())",
        category="Fecha"
    ),
    "DAY": ExcelFormula(
        name_spanish="DIA",
        name_english="DAY",
        description="Extrae el día del mes (1-31).",
        example="DAY(Fecha_Factura)",
        category="Fecha"
    ),
    "WEEKDAY": ExcelFormula(
        name_spanish="DIASEM",
        name_english="WEEKDAY",
        description="Devuelve el día de la semana numérico.",
        example="WEEKDAY(Fecha_Cita)",
        category="Fecha",
        note="0 = Lunes, 6 = Domingo (Formato Python)."
    )
}