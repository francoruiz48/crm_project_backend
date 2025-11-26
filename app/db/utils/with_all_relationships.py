from sqlalchemy.orm import joinedload, class_mapper


def with_all_relationships(query, model):
    """
    Aplica joinedload() a todas las relaciones del modelo.
    Evita los DetachedInstanceError al devolver objetos con relaciones cargadas.
    """
    mapper = class_mapper(model)
    for rel in mapper.relationships:
        # joinedload necesita el atributo del modelo, no un string
        query = query.options(joinedload(getattr(model, rel.key)))
    return query
