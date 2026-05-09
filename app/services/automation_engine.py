from typing import Dict, Any, Tuple
from datetime import datetime
from sqlalchemy.orm import Session

from app.models.field_automation import FieldAutomation
from app.schemas.field_automation_schema import (
    RuleGroup, RuleCondition, LogicalOperatorEnum, 
    ConditionOperatorEnum, ActionTypeEnum, AutomationAction
)
from app.core.constans import DATE_FORMAT, DATE_TIME_FORMAT

class AutomationEngine:
    
    # Límite de veces que el motor re-evaluará las reglas si hay cambios (Efecto Dominó)
    MAX_CASCADES = 5 
    
    # Límite de grupos anidados permitidos en el JSON para evitar Stack Overflow
    MAX_JSON_DEPTH = 10 

    @classmethod
    def run(cls, session: Session, campaign_id: int, context_data: Dict[int, Any], event: str) -> Tuple[Dict[int, Any], Dict[int, dict]]:
        audit_log = {}
        
        rules = session.query(FieldAutomation).filter(
            FieldAutomation.campaign_id == campaign_id,
            FieldAutomation.active == True,
            FieldAutomation.trigger_events.contains([event])
        ).order_by(FieldAutomation.priority.asc()).all()

        if not rules:
            return context_data, audit_log

        # --- DEFENSA 1: Bucle de Cascada con Límite ---
        iterations = 0
        state_changed = True
        
        while state_changed and iterations < cls.MAX_CASCADES:
            state_changed = False
            iterations += 1
            
            for rule_db in rules:
                try:
                    conditions_tree = RuleGroup.model_validate(rule_db.conditions)
                    
                    if cls._evaluate_group(conditions_tree, context_data, current_depth=1):
                        
                        actions_list = [AutomationAction.model_validate(a) for a in rule_db.actions]
                        # Retorna True si AL MENOS UN campo mutó realmente
                        changed_in_rule = cls._apply_actions(actions_list, context_data, audit_log, rule_db.name)
                        
                        if changed_in_rule:
                            state_changed = True
                            
                except Exception as e:
                    print(f"⚠️ Error evaluando regla '{rule_db.name}': {e}")
                    continue

        if iterations >= cls.MAX_CASCADES:
            # Puedes lanzar un HTTPException aquí si prefieres ser estricto, 
            # pero degradar elegantemente (solo advertir) suele dar mejor UX.
            print(f"⚠️ ATENCIÓN: Límite de cascada alcanzado ({cls.MAX_CASCADES}) para campaña {campaign_id}.")

        return context_data, audit_log

    # ==========================================
    # EL MOTOR LÓGICO (RECURSIVIDAD BLINDADA)
    # ==========================================
    @classmethod
    def _evaluate_group(cls, group: RuleGroup, context: Dict[int, Any], current_depth: int) -> bool:
        # --- DEFENSA 2: Cortafuegos de Stack Overflow ---
        if current_depth > cls.MAX_JSON_DEPTH:
            print(f"⚠️ Profundidad máxima de JSON alcanzada ({cls.MAX_JSON_DEPTH}).")
            return False

        results = []
        for node in group.rules:
            if isinstance(node, RuleGroup):
                results.append(cls._evaluate_group(node, context, current_depth + 1))
            elif isinstance(node, RuleCondition):
                results.append(cls._evaluate_condition(node, context))

        if not results:
            return False # Un grupo vacío no cumple nada

        if group.operator == LogicalOperatorEnum.AND:
            return all(results)
        elif group.operator == LogicalOperatorEnum.OR:
            return any(results)
            
        return False

    @classmethod
    def _evaluate_condition(cls, condition: RuleCondition, context: Dict[int, Any]) -> bool:
        actual_val = context.get(condition.field_id)
        target_val = condition.value
        op = condition.operator

        # --- MAGIA: Variables de Macro (Fechas relativas) ---
        if isinstance(target_val, str):
            if target_val == "{{CURRENT_DATE}}":
                target_val = datetime.utcnow().strftime(DATE_FORMAT)
            elif target_val == "{{CURRENT_DATETIME}}":
                # Usá tu constante DATE_TIME_FORMAT aquí si la tenés importada
                target_val = datetime.utcnow().strftime(DATE_TIME_FORMAT)

        is_empty = actual_val is None or actual_val == "" or actual_val == []
        if op == ConditionOperatorEnum.IS_EMPTY: return is_empty
        if op == ConditionOperatorEnum.IS_NOT_EMPTY: return not is_empty

        if is_empty: return False

        def _to_set(val):
            if isinstance(val, list): return set(str(v).strip() for v in val)
            return {str(val).strip()}

        print(f"Evaluando condición: Campo {condition.field_id} {op} '{condition.value}' (Valor actual: '{actual_val}', Valor objetivo procesado: '{target_val}')")
        if op == ConditionOperatorEnum.EQUALS:
            return _to_set(actual_val) == _to_set(target_val)
            
        if op == ConditionOperatorEnum.NOT_EQUALS:
            return _to_set(actual_val) != _to_set(target_val)
            
        if op == ConditionOperatorEnum.CONTAINS:
            return _to_set(target_val).issubset(_to_set(actual_val))
            
        if op == ConditionOperatorEnum.NOT_CONTAINS:
            return not _to_set(target_val).issubset(_to_set(actual_val))

        # --- COMPARACIÓN INTELIGENTE (Números y Fechas) ---
        if op in (ConditionOperatorEnum.GREATER_THAN, ConditionOperatorEnum.LESS_THAN):
            try:
                # 1. Intentamos comparar numéricamente (vital para que 10 sea mayor que 2)
                val_a = float(actual_val)
                val_t = float(target_val)
                if op == ConditionOperatorEnum.GREATER_THAN: return val_a > val_t
                if op == ConditionOperatorEnum.LESS_THAN: return val_a < val_t
            except (ValueError, TypeError):
                # 2. Fallback a String. 
                # ¡Las fechas en formato YYYY-MM-DD se ordenan y comparan perfectamente así!
                str_a = str(actual_val).strip()
                str_t = str(target_val).strip()
                if op == ConditionOperatorEnum.GREATER_THAN: return str_a > str_t
                if op == ConditionOperatorEnum.LESS_THAN: return str_a < str_t

        return False

    # ==========================================
    # EL MOTOR DE ACCIONES (MUTACIÓN)
    # ==========================================
    @classmethod
    def _apply_actions(cls, actions: list[AutomationAction], context: Dict[int, Any], audit_log: Dict[int, dict], rule_name: str) -> bool:
        any_change = False
        
        for action in actions:
            target_id = action.target_field_id
            old_value = context.get(target_id)
            new_value = None

            if action.type == ActionTypeEnum.SET_VALUE:
                new_value = action.value

            elif action.type == ActionTypeEnum.CLEAR_VALUE:
                new_value = None

            elif action.type == ActionTypeEnum.SET_CURRENT_DATE:
                new_value = datetime.utcnow().strftime(DATE_FORMAT)

            elif action.type == ActionTypeEnum.SET_CURRENT_DATETIME: 
                new_value = datetime.utcnow().strftime(DATE_TIME_FORMAT)

            elif action.type == ActionTypeEnum.COPY_FROM_FIELD:
                # Solo copiamos si el origen existe y no está vacío
                if action.source_field_id and action.source_field_id in context:
                    new_value = context[action.source_field_id]
                else:
                    new_value = old_value # Anula la operación si falla el origen

            # --- DEFENSA 3: Solo guardamos si el valor REALMENTE mutó ---
            if str(old_value) != str(new_value):
                context[target_id] = new_value
                
                # Actualizamos o creamos el log de este campo
                # Si otra regla ya lo había tocado antes, pisamos el new_value y el source_rule,
                # pero mantenemos el old_value original intacto para la auditoría final.
                if target_id in audit_log:
                    audit_log[target_id]["new_value"] = new_value
                    audit_log[target_id]["source_rule"] = f"{audit_log[target_id]['source_rule']} -> {rule_name}"
                else:
                    audit_log[target_id] = {
                        "old_value": old_value,
                        "new_value": new_value,
                        "source_rule": rule_name
                    }
                any_change = True
                
        return any_change