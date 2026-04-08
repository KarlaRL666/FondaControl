-- Trigger opcional: solo para respaldo, la lógica principal vive en Python.
-- Se dispara solo cuando una producción cambia a Completada.

DELIMITER $$

DROP TRIGGER IF EXISTS trg_descontar_insumos_produccion $$

CREATE TRIGGER trg_descontar_insumos_produccion
AFTER UPDATE ON producciones
FOR EACH ROW
BEGIN
    IF NEW.estado = 'Completada' AND OLD.estado <> 'Completada' THEN
        UPDATE materias_primas mp
        JOIN (
            SELECT
                rd.id_materia,
                SUM(
                    (
                        (rd.cantidad_requerida * (dp.cantidad / NULLIF(r.cantidad_produccion, 0)))
                        * (1 + (COALESCE(mp2.porcentaje_merma, 0) / 100))
                    )
                ) AS cantidad_descontar
            FROM detalle_produccion dp
            JOIN recetas r ON r.id_producto = dp.id_producto AND r.estado = 1
            JOIN receta_detalle rd ON rd.id_receta = r.id_receta
            JOIN materias_primas mp2 ON mp2.id_materia = rd.id_materia
            WHERE dp.id_produccion = NEW.id_produccion
            GROUP BY rd.id_materia
        ) req ON req.id_materia = mp.id_materia
        SET mp.stock_actual = mp.stock_actual - req.cantidad_descontar;
    END IF;
END $$

DELIMITER ;
