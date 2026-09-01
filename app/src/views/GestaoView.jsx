import { lazy, Suspense, useState } from "react";
import SugestoesVinculoView from "./SugestoesVinculoView";

// Carregadas sob demanda: a tela de importação e a lista completa só são
// abertas pelo gerente, e de vez em quando — não faz sentido pesarem no
// pacote que o vendedor baixa no celular em campo.
const CarteiraAdminView = lazy(() => import("./CarteiraAdminView"));
const ImportarView = lazy(() => import("./ImportarView"));
const AjustesView = lazy(() => import("./AjustesView"));

const ABAS = [
  { id: "clientes", rotulo: "Todos os clientes", descricao: "Buscar, vincular, inativar e achar quem está sem localização" },
  { id: "sugestoes", rotulo: "Sugestões de vínculo", descricao: "Candidatos a mesma empresa encontrados automaticamente" },
  { id: "importar", rotulo: "Importar", descricao: "Atualizar a carteira com o banco mestre ou o relatório de vendas" },
  { id: "ajustes", rotulo: "Ajustes", descricao: "Regras do negócio que você controla" },
];

// Área de gestão da carteira (só Admin). Reúne o que antes era só a fila de
// sugestões de vínculo: agora tem também a lista completa de clientes, a
// importação e os ajustes.
export default function GestaoView() {
  const [aba, setAba] = useState("clientes");
  const atual = ABAS.find((a) => a.id === aba);

  return (
    <div className="gestao">
      <div className="gestao-cabecalho">
        <div className="subtabs">
          {ABAS.map((a) => (
            <button
              key={a.id}
              className={"subtab" + (aba === a.id ? " on" : "")}
              onClick={() => setAba(a.id)}
            >
              {a.rotulo}
            </button>
          ))}
        </div>
        <p className="muted" style={{ fontSize: 13 }}>{atual.descricao}</p>
      </div>

      <div className="gestao-corpo">
        <Suspense fallback={<p className="muted">Carregando…</p>}>
          {aba === "clientes" && <CarteiraAdminView />}
          {aba === "sugestoes" && <SugestoesVinculoView />}
          {aba === "importar" && <ImportarView />}
          {aba === "ajustes" && <AjustesView />}
        </Suspense>
      </div>
    </div>
  );
}
