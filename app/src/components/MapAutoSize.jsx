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
    // se o container estiver escondido (display:none — ex.: modo "filtro" no
    // mobile, com o mapa fora de tela), o tamanho é 0x0; recalcular nesse
    // estado corrompe a posição interna do Leaflet (dispara moveend com
    // limites inválidos) — ignora até o container ter tamanho de verdade.
    const fix = () => {
      const { width, height } = map.getContainer().getBoundingClientRect();
      if (width > 0 && height > 0) map.invalidateSize();
    };
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
