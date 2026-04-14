import operator
import random
import re
from datetime import datetime, date
from app.core.constans import DATE_FORMAT

class ExcelFormulaEvaluatorService:
    def __init__(self, context=None):
        self.context = context or {}
        
        def _safe_math(op_func, a, b):
            try:
                if a is None: a = 0
                if b is None: b = 0
                return op_func(float(a), float(b))
            except (ValueError, TypeError):
                raise ValueError("Se esperaba un valor numérico para la operación matemática.")

        # Operadores soportados
        self.operators = {
            '+': lambda a, b: _safe_math(operator.add, a, b),
            '-': lambda a, b: _safe_math(operator.sub, a, b),
            '*': lambda a, b: _safe_math(operator.mul, a, b),
            '/': lambda a, b: _safe_math(operator.truediv, a, b),
            
            # Comparadores que usan _safe_compare
            '>': lambda a, b: self._safe_compare(operator.gt, a, b),
            '<': lambda a, b: self._safe_compare(operator.lt, a, b),
            '>=': lambda a, b: self._safe_compare(operator.ge, a, b),
            '<=': lambda a, b: self._safe_compare(operator.le, a, b),
            
            # Igualdad: manejo laxo de string vs number
            '=': lambda a, b: self._safe_compare(operator.eq, a, b), 
            '<>': lambda a, b: not self._safe_compare(operator.eq, a, b),
            
            '&': operator.add
        }

        self.func_map = {
            # Regex
            'REGEXMATCH': self._regex_match, 
            'REGEX': self._regex_match,

            # Lógica
            'AND': all, 'Y': all,
            'OR': any, 'O': any,
            'NOT': self._not, 'NO': self._not,
            
            # Texto
            'CONCAT': self._concat, 'CONCATENATE': self._concat,
            'LEN': self._len, 'LARGO': self._len,
            'LOWER': self._lower, 'MINUSCULA': self._lower,
            'UPPER': self._upper, 'MAYUSCULA': self._upper,
            'LEFT': self._left, 'IZQUIERDA': self._left,
            'RIGHT': self._right, 'DERECHA': self._right,
            'MID': self._mid, 'EXTRAE': self._mid,
            'TEXT': self._text, 'TEXTO': self._text,
            'TRIM': self._trim, 'ESPACIOS': self._trim,
            'SUBSTITUTE': self._substitute, 'SUSTITUIR': self._substitute, 'REPLACE': self._substitute,
            'PROPER': self._proper, 'NOMPROPIO': self._proper,
            'FIND': self._find, 'ENCONTRAR': self._find, 'HALLAR': self._find,

            #Números
            'ROUND': self._round, 'REDONDEAR': self._round,
            'INT': self._int, 'ENTERO': self._int,
            'ABS': self._abs, 'VALORABSOLUTO': self._abs,
            'SQRT': self._sqrt, 'RAIZCUADRADA': self._sqrt,
            'POWER': self._power, 'POTENCIA': self._power,
            'MOD': self._mod, 'RESIDUO': self._mod,
            'FLOOR': self._floor, 'REDONDEAR.MENOS': self._floor,
            'CEIL': self._ceil, 'REDONDEAR.MAS': self._ceil,
            'SIGN': self._sign, 'SIGNO': self._sign,
            'RANDOM': self._random_number, 'ALEATORIO': self._random_number,
            'RANDOM_BETWEEN': self._random_between, 'ALEATORIO.ENTRE': self._random_between,
            'ISNUMBER': self._is_number, 'ESNUMERO': self._is_number,

            # Matemáticas / Estadística
            'SUM': self._sum, 'SUMA': self._sum,
            'AVERAGE': self._avg, 'PROMEDIO': self._avg,
            'COUNT': self._count, 'CONTAR': self._count,
            'MAX': self._max,
            'MIN': self._min,

            # Fecha y Hora
            'NOW': self._now, 'AHORA': self._now,
            'TODAY': self._today, 'HOY': self._today,
            'DAY': self._day, 'DIA': self._day,
            'YEAR': self._year, 'ANO': self._year, 'AÑO': self._year,
            'MONTH': self._month, 'MES': self._month,
            'HOUR': self._hour, 'HORA': self._hour,
            'MINUTE': self._minute, 'MINUTO': self._minute,
            'SECOND': self._second, 'SEGUNDO': self._second,

            #Otras
            'WEEKDAY': self._weekday, 'DIASEM': self._weekday
        }

    def _safe_compare(self, op_func, a, b):
        """
        Helper para comparar valores permitiendo strings numéricos ("5" > 4).
        Intenta convertir a float. Si falla, compara como strings.
        """
        try:
            # Intentamos convertir ambos a float para comparación numérica
            fa = float(a)
            fb = float(b)
            return op_func(fa, fb)
        except (ValueError, TypeError):
            # Fallback: comparación de strings (alfanumérica)
            return op_func(str(a), str(b))

    def evaluate(self, expression):
        if not expression: return None
        
        # 1. Quitamos el '=' inicial si existe (típico de Excel)
        expression = expression.strip()
        if expression.startswith('='): expression = expression[1:]

        # 2. PRE-PROCESAMIENTO: Manejo de variables entre {}
        # Reemplaza {variable} por su valor formateado. Si es texto, lo entrecomilla.
        if self.context:
            for var_name, var_value in self.context.items():
                pattern = r"\{" + re.escape(str(var_name)) + r"\}"
                
                if var_value is None:
                    replacement = '""' # Tratamos los nulos como string vacío en formulas
                elif isinstance(var_value, (int, float)):
                    replacement = str(var_value)
                else:
                    # Todo lo demás (fechas, texto) lo envolvemos en comillas para el parser
                    replacement = f'"{str(var_value)}"'
                
                # Usamos regex ignorando mayúsculas/minúsculas por conveniencia
                expression = re.sub(pattern, replacement, expression, flags=re.IGNORECASE)

        try:
            return self._parse_expression(expression)
        except Exception as e:
            # En producción, logguear esto
            return f"#ERROR: {str(e)}"

    def _parse_expression(self, expr):
        expr = expr.strip()
        
        while expr.startswith('(') and expr.endswith(')'):
            # Verificamos si los paréntesis realmente envuelven TODO el contenido
            # Ejemplo válido: (A - B) -> Se quitan
            # Ejemplo inválido: (A) - (B) -> No se quitan (se procesa el - después)
            depth = 0
            is_wrapped = True
            for i, char in enumerate(expr[:-1]): # Recorremos hasta el anteúltimo
                if char == '(': depth += 1
                elif char == ')': depth -= 1
                
                # Si la profundidad llega a 0 antes del final, no es un grupo único
                if depth == 0:
                    is_wrapped = False
                    break
            
            if is_wrapped:
                expr = expr[1:-1].strip()
            else:
                break

        # 1. Es un número?
        try:
            if "." in expr: return float(expr)
            return int(expr)
        except ValueError:
            pass
        
        # 2. Es un string literal? ("Hola")
        if expr.startswith('"') and expr.endswith('"'):
            return expr[1:-1]
        
        # 3. Es una variable del contexto? (ej: ciudad)
        if expr in self.context:
            val = self.context[expr]
            
            if val is None:
                return None
                
            # Normalizamos fechas para poder compararlas
            if isinstance(val, (date, datetime)): 
                return val
                
            # SI ES STRING NUMÉRICO, LO CONVERTIMOS A FLOAT
            if isinstance(val, str):
                val_trimmed = val.strip()
                # Verificar si es un número positivo o negativo (con o sin decimal)
                if val_trimmed.replace('.', '', 1).replace('-', '', 1).isdigit():
                    # Si termina en .0, lo podemos tratar como int, sino como float
                    try:
                        return float(val_trimmed) if '.' in val_trimmed else int(val_trimmed)
                    except ValueError:
                        return val # Fallback seguro
            
            return val

        # 4. Es una función? IF(...), CONCAT(...)
        match = re.match(r'^([A-Z]+)\((.*)\)$', expr, re.DOTALL)
        if match:
            # VALIDACIÓN CRÍTICA: Verificar que no sea un "falso positivo"
            # Ejemplo: YEAR(A) - YEAR(B) -> El regex cree que es una función YEAR gigante.
            # Verificamos si el paréntesis de cierre real está al final de la cadena.
            
            func_name = match.group(1)
            open_idx = expr.find('(')
            
            depth = 0
            actual_close_idx = -1
            for i, char in enumerate(expr[open_idx:], start=open_idx):
                if char == '(': depth += 1
                elif char == ')': depth -= 1
                
                if depth == 0:
                    actual_close_idx = i
                    break
            
            # Solo ejecutamos como función si cierra EXACTAMENTE al final
            if actual_close_idx == len(expr) - 1:
                args_str = match.group(2)
                args = self._split_args(args_str)
                return self._execute_function(func_name, args)

        # 5. Es una operación matemática/lógica simple? (A > B, A + B)
        # Esto es un parser simplificado, busca el operador de menor precedencia
        operators_priority = [
            '<>', '>=', '<=',  # Multi-caracter PRIMERO
            '=', '>', '<',     # Single-caracter DESPUÉS
            '&', '+', '-', '*', '/' # Matemáticos
        ]

        for op_symbol in operators_priority:
            # Buscamos el operador pero ignorando lo que esté dentro de paréntesis
            split_idx = self._find_operator_index(expr, op_symbol)
            if split_idx != -1:
                left = expr[:split_idx]
                right = expr[split_idx + len(op_symbol):]
                
                val_left = self._parse_expression(left)
                val_right = self._parse_expression(right)
                
                # Manejo especial para concatenar strings con nulos
                if op_symbol == '&': 
                    val_left = str(val_left) if val_left is not None else ""
                    val_right = str(val_right) if val_right is not None else ""

                return self.operators[op_symbol](val_left, val_right)

        # Si llegamos acá y parece texto sin comillas, asumimos que es un string directo o variable nula
        return expr

    def _execute_function(self, name, args_raw):
        # Evaluación LAZY para IF: Solo evaluamos la rama necesaria
        if name == 'IF':
            if len(args_raw) != 3: raise ValueError("IF requiere 3 argumentos")
            condition = self._parse_expression(args_raw[0])
            if condition:
                return self._parse_expression(args_raw[1])
            else:
                return self._parse_expression(args_raw[2])

        # Para otras funciones, evaluamos todos los argumentos primero
        args = [self._parse_expression(a) for a in args_raw]

        if name in self.func_map:
            try:
                return self.func_map[name](args)
            except Exception as e:
                return f"#ERROR: {name} fallo ({str(e)})"
        
        raise ValueError(f"Función desconocida: {name}")

    # --- IMPLEMENTACIÓN DE FUNCIONES ---
    # Texto
    def _concat(self, args):
        return "".join([str(a) for a in args if a is not None])

    def _len(self, args):
        return len(str(args[0]))

    def _lower(self, args):
        return str(args[0]).lower() if args[0] else ""

    def _upper(self, args):
        return str(args[0]).upper() if args[0] else ""

    def _left(self, args):
        # IZQUIERDA(texto, n)
        text = str(args[0])
        n = int(args[1])
        return text[:n]

    def _right(self, args):
        # DERECHA(texto, n)
        text = str(args[0])
        n = int(args[1])
        return text[-n:]

    def _mid(self, args):
        # EXTRAE(texto, inicio, cantidad)
        # OJO: Excel empieza en 1, Python en 0. Hacemos la corrección aquí.
        text = str(args[0])
        start = int(args[1]) - 1 
        length = int(args[2])
        if start < 0: start = 0
        return text[start : start + length]

    # Matemáticas
    def _sum(self, args):
        # SUMA(arg1, arg2, arg3...) filtra nulos y convierte a float/int
        total = 0
        for x in args:
            if isinstance(x, (int, float)): total += x
            elif isinstance(x, str) and x.replace('.','',1).isdigit(): total += float(x)
        return total

    def _avg(self, args):
        # PROMEDIO(arg1, arg2...)
        numeros = [float(x) for x in args if isinstance(x, (int, float)) or (isinstance(x, str) and x.replace('.','',1).isdigit())]
        if not numeros: return 0
        return sum(numeros) / len(numeros)

    def _count(self, args):
        # CONTAR(...) Cuenta valores no nulos
        return len([x for x in args if x is not None])

    def _max(self, args):
        # Filtramos para evitar error comparando str con int
        validos = [x for x in args if isinstance(x, (int, float))]
        if not validos: return 0
        return max(validos)

    def _min(self, args):
        validos = [x for x in args if isinstance(x, (int, float))]
        if not validos: return 0
        return min(validos)
    
    #Numeros
    def _round(self, args):
        val = float(args[0])
        digits = int(args[1]) if len(args) > 1 else 0
        return round(val, digits)
    
    def _int(self, args):
        val = float(args[0])
        return int(val)
    
    def _abs(self, args):
        val = float(args[0])
        return abs(val)
    
    def _sqrt(self, args):
        val = float(args[0])
        if val < 0:
            raise ValueError("No se puede calcular la raíz cuadrada de un número negativo")
        return val ** 0.5
    
    def _power(self, args):
        base = float(args[0])
        exponent = float(args[1])
        return base ** exponent
    
    def _mod(self, args):
        dividend = int(args[0])
        divisor = int(args[1])
        if divisor == 0:
            raise ValueError("División por cero en MOD")
        return dividend % divisor
    
    def _random_between(self, args):
        from_ = int(args[0])
        until_ = int(args[1])
        return random.randint(from_, until_)
    
    def _random_number(self):
        return random.random()
    
    def _is_number(self, args):
        val = args[0]
        if val is None: return False
        if isinstance(val, (int, float)): return True
        if isinstance(val, str):
            try:
                float(val)
                return True
            except ValueError:
                return False
        return False

    #Redondeo hacia abajo
    def _floor(self, args):
        import math
        val = float(args[0])
        return math.floor(val)
    
    #Redondeo hacia arriba
    def _ceil(self, args):
        import math
        val = float(args[0])
        return math.ceil(val)
    
    # Devuelve el signo de un número
    def _sign(self, args):
        val = float(args[0])
        if val > 0:
            return 1
        elif val < 0:
            return -1
        else:
            return 0

    # Fechas
    def _now(self, args):
        return datetime.now() # Retorna objeto datetime

    def _today(self, args):
        return date.today() # Retorna objeto date

    def _day(self, args):
        val = args[0]
        if isinstance(val, (datetime, date)): return val.day
        # Si es string, intentamos parsear ISO básico
        try:
            return datetime.strptime(str(val)[:10], DATE_FORMAT).day
        except:
            return 0

    def _month(self, args):
        val = args[0]
        if isinstance(val, (datetime, date)): return val.month
        try:
            return datetime.strptime(str(val)[:10], DATE_FORMAT).month
        except:
            return 0
            
    def _year(self, args):
        val = args[0]
        if isinstance(val, (datetime, date)): return val.year
        try:
            return datetime.strptime(str(val)[:10], DATE_FORMAT).year
        except:
            return 0

    def _hour(self, args):
        val = args[0]
        if isinstance(val, datetime): return val.hour
        try:
            return datetime.strptime(str(val), DATE_FORMAT + " %H:%M:%S").hour
        except:
            return 0

    def _minute(self, args):
        val = args[0]
        if isinstance(val, datetime): return val.minute
        try:
            return datetime.strptime(str(val), DATE_FORMAT + " %H:%M:%S").minute
        except:
            return 0

    def _second(self, args):
        val = args[0]
        if isinstance(val, datetime): return val.second
        try:
            return datetime.strptime(str(val), DATE_FORMAT + " %H:%M:%S").second
        except:
            return 0
        
    def _text(self, args):
        return str(args[0])
    
    def _weekday(self, args):
        """
        Retorna el día de la semana.
        Estándar Python: 0=Lunes, 1=Martes, ..., 5=Sábado, 6=Domingo.
        """
        val = args[0]
        
        # 1. Si ya es un objeto fecha, devolvemos directo
        if isinstance(val, (datetime, date)): 
            return val.weekday()
        
        # 2. Si es string, intentamos parsear
        s_val = str(val)
        try:
            # Intento 1: Fecha sola (YYYY-MM-DD)
            return datetime.strptime(s_val[:10], DATE_FORMAT).weekday()
        except ValueError:
            try:
                # Intento 2: Fecha y Hora (YYYY-MM-DD HH:MM:SS)
                # Asumiendo que DATE_TIME_FORMAT está disponible o hardcodeado
                return datetime.strptime(s_val, "%Y-%m-%d %H:%M:%S").weekday()
            except ValueError:
                return 0 # O manejar error si prefieres
        
    # Regex
    def _regex_match(self, args):
        # Sintaxis: REGEXMATCH(texto, patron)
        text = str(args[0])
        pattern = str(args[1])
        return bool(re.search(pattern, text))
    
    def _trim(self, args):
        """Elimina espacios al inicio y al final"""
        val = str(args[0]) if args[0] is not None else ""
        return val.strip()

    def _substitute(self, args):
        """
        Sintaxis: SUBSTITUTE(texto, texto_viejo, texto_nuevo)
        Ej: SUBSTITUTE("123-456", "-", "") -> "123456"
        """
        text = str(args[0]) if args[0] is not None else ""
        old_text = str(args[1]) if len(args) > 1 else ""
        new_text = str(args[2]) if len(args) > 2 else ""
        
        return text.replace(old_text, new_text)

    def _proper(self, args):
        """Convierte a Título: 'juan perez' -> 'Juan Perez'"""
        val = str(args[0]) if args[0] is not None else ""
        return val.title()

    def _not(self, args):
        """Invierte un booleano"""
        val = args[0]
        # Manejo robusto de falsy values de Excel
        if isinstance(val, bool): return not val
        if val == 0: return True
        if val == 1: return False
        return not bool(val)
    
    def _find(self, args):
        """
        Devuelve la posición de un texto dentro de otro.
        Sintaxis: FIND(texto_buscado, texto_donde_buscar)
        OJO: Excel retorna índice base 1. Si no encuentra, Excel da error.
        Aquí retornaremos 0 si no encuentra para facilitar condiciones IF(FIND(...) > 0, ...)
        """
        find_text = str(args[0])
        within_text = str(args[1])
        
        # Python find retorna -1 si no encuentra, y es base 0.
        # Ajustamos a base 1 para Excel.
        pos = within_text.find(find_text)
        if pos == -1:
            return 0
        return pos + 1

    # --- HELPERS DE PARSING ---
    def _split_args(self, args_str):
        args = []
        current = ""
        depth = 0
        in_quotes = False
        
        for char in args_str:
            if char == '"': in_quotes = not in_quotes
            if in_quotes:
                current += char
                continue
            if char == '(': depth += 1
            elif char == ')': depth -= 1
            
            if char == ',' and depth == 0:
                args.append(current.strip())
                current = ""
            else:
                current += char
        
        if current: args.append(current.strip())
        return args

    def _find_operator_index(self, expr, op):
        depth = 0
        in_quotes = False
        op_len = len(op)
        for i in range(len(expr)):
            char = expr[i]
            if char == '"': in_quotes = not in_quotes
            if in_quotes: continue
            if char == '(': depth += 1
            elif char == ')': depth -= 1
            
            if depth == 0 and expr[i:i+op_len] == op:
                return i
        return -1