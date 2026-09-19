import { ORIGENS } from "../lib/potencial";

// Escolha "antigos / novos / todos" e "só potencial ouro" — a mesma nas quatro telas.
// `contagem` (opcional) mostra quantos clientes têm potencial na lista de origem.
export default function FiltroPotencial({ filtro, aoMudar, contagem }) {
  return (
    <div className="filtro-grupo filtro-potencial">
      <span className="filtro-titulo">Clientes</span>
      <div className="subtabs">
        {ORIGENS.map((o) => (
          <button
            key={o.id}
            type="button"
            className={"subtab" + (filtro.origem === o.id ? " on" : "")}
            onClick={() => aoMudar({ origem: o.id })}
          >
            {o.rotulo}
          </button>
        ))}
      </div>

      <label
        className="ficha-radio"
        style={{ fontSize: 13, marginTop: 8 }}
        title="Mostra só quem tem nota de potencial ouro. Prata, bronze e clientes novos com bom perfil; ouro fica de fora."
      >
        <input
          type="checkbox"
          checked={filtro.soPotencial}
          onChange={(e) => aoMudar({ soPotencial: e.target.checked })}
        />
        Só potencial ouro{typeof contagem === "number" ? ` (${contagem})` : ""}
      </label>

      {filtro.soPotencial && (
        <label className="faint" style={{ fontSize: 12, display: "flex", alignItems: "center", gap: 6, marginTop: 4 }}>
          nota mínima
          <input
            className="input"
            type="number" min="0" max="100" step="5"
            style={{ width: 70 }}
            value={filtro.notaMin}
            onChange={(e) => aoMudar({ notaMin: Math.max(0, Math.min(100, Number(e.target.value) || 0)) })}
          />
        </label>
      )}
    </div>
  );
}
