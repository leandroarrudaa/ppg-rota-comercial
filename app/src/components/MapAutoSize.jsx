import { useEffect } from "react";
import { useMap } from "react-leaflet";

/**
 * Corrige o bug clássico do Leaflet em que o mapa é inicializado antes do
 * container ter a altura final (layouts flex/grid) e só renderiza os tiles
 * numa faixa. Força invalidateSize quando o container assenta ou muda de tamanho.
 */
export default function MapAutoSize() {
  const map = useMap();
  useEffect(() => {
    const fix = () => map.invalidateSize();
    const t1 = setTimeout(fix, 0);
    const t2 = setTimeout(fix, 250);
    const ro = new ResizeObserver(fix);
    ro.observe(map.getContainer());
    window.addEventListener("resize", fix);
    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
      ro.disconnect();
      window.removeEventListener("resize", fix);
    };
  }, [map]);
  return null;
}
