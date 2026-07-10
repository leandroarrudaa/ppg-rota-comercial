import { useMemo, useState } from "react";
import VisitasView from "./VisitasView";
import ContatoView from "./ContatoView";

export default function PlanoView({ clientes }) {
  const [sub, setSub] = useState("Visitas");
  const [meses, setMeses] = useState(6); // "ativo" = comprou nos últimos N meses

  const { ativos, adormecidos } = useMemo(() => {
    const corte = meses * 30;
    const ativos = [];
    const adormecidos = [];
    for (const c of clientes) {
      if (c.recencia == null) continue;
      if (c.recencia <= corte) ativos.push(c);
      else adormecidos.push(c);
    }
    return { ativos, adormecidos };
  }, [clientes, meses]);

  return (
    <div className="plano-wrap">
      <div className="subtabs-bar">
        <div className="subtabs">
          <button className={"subtab" + (sub === "Visitas" ? " on" : "")} onClick={() => setSub("Visitas")}>
            Plano de Visitas <b>{ativos.length}</b>
          </button>
          <button className={"subtab" + (sub === "Contato" ? " on" : "")} onClick={() => setSub("Contato")}>
            Plano de Contato <b>{adormecidos.length}</b>
          </button>
        </div>

        <div className="corte">
          <span className="faint">Considera ativo quem comprou nos últimos</span>
          <input
            type="range" min="2" max="18" value={meses}
            onChange={(e) => setMeses(+e.target.value)}
            className="slider corte-slider"
          />
          <b>{meses} meses</b>
        </div>
      </div>

      <div className="plano-corpo">
        {sub === "Visitas" ? <VisitasView clientes={ativos} /> : <ContatoView clientes={adormecidos} />}
      </div>
    </div>
  );
}
