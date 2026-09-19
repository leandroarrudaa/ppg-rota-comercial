import { FAIXA_CHIP, FAIXA_DOT } from "../lib/format";

// Chip da faixa RFM; cliente novo (sem faixa) mostra "Novo". Se tiver nota de
// potencial, ela vem junto — o texto do detalhe (como a nota foi montada) fica no title.
export default function ChipFaixa({ c, semTexto = false }) {
  return (
    <>
      {c.faixa ? (
        <span className={"chip " + FAIXA_CHIP[c.faixa]}>
          <span className={"dot " + FAIXA_DOT[c.faixa]} />{semTexto ? "" : c.faixa}
        </span>
      ) : (
        <span className="chip chip-motivo">{semTexto ? "N" : "Novo"}</span>
      )}
      {c.notaPotencial != null && (
        <span className="chip chip-potencial" title={c.potencialDetalhe || "Nota de potencial ouro"}>
          ★ {c.notaPotencial}
        </span>
      )}
    </>
  );
}
