# Puerta de entrada a todos los comandos del proyecto.
# Se amplía en H1 tarea 3 (setup, check-docs, check-skills, mapa).

.PHONY: check check-private

check: check-private ## Todas las verificaciones

check-private: ## Falla si algo de la capa privada quedó versionado
	@scripts/check_private.sh
