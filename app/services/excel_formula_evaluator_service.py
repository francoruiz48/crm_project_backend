import operator
import re
from datetime import datetime, date
from app.core.constans import DATE_FORMAT

class ExcelFormulaEvaluatorService:
    def __init__(self, context=None):
        self.context = context or {}
        
        # Operadores soportados
        self.operators = {
            '+': operator.add, '-': operator.sub, '*': operator.mul, '/': operator.truediv,
            '>': operator.gt, '<': operator.lt, '>=': operator.ge, '<=': operator.le,
            '=': operator.eq, '<>': operator.ne, '&': operator.add
        }

        self.func_map = {
            # Lógica
            'AND': all, 'Y': all,
            'OR': any, 'O': any,
            
            # Texto
            'CONCAT': self._concat, 'CONCATENATE': self._concat,
            'LEN': self._len, 'LARGO': self._len,
            'LOWER': self._lower, 'MINUSCULA': self._lower,
            'UPPER': self._upper, 'MAYUSCULA': self._upper,
            'LEFT': self._left, 'IZQUIERDA': self._left,
            'RIGHT': self._right, 'DERECHA': self._right,
            'MID': self._mid, 'EXTRAE': self._mid,

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
        }

    def evaluate(self, expression):
        if not expression: return None
        # Quitamos el '=' inicial si existe (típico de Excel)
        expression = expression.strip()
        if expression.startswith('='): expression = expression[1:]
        
        try:
            return self._parse_expression(expression)
        except Exception as e:
            # En producción, logguear esto
            return f"#ERROR: {str(e)}"

    def _parse_expression(self, expr):
        expr = expr.strip()
        
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
            # Normalizamos fechas para poder compararlas
            if isinstance(val, (date, datetime)): return val
            return val

        # 4. Es una función? IF(...), CONCAT(...)
        match = re.match(r'^([A-Z]+)\((.*)\)$', expr, re.DOTALL)
        if match:
            func_name = match.group(1)
            args_str = match.group(2)
            args = self._split_args(args_str)
            return self._execute_function(func_name, args)

        # 5. Es una operación matemática/lógica simple? (A > B, A + B)
        # Esto es un parser simplificado, busca el operador de menor precedencia
        for op_symbol in ['=', '<>', '>', '<', '>=', '<=', '&', '+', '-', '*', '/']:
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