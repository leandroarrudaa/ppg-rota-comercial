import { TileLayer } from "react-leaflet";

// Chave do CARTO Basemaps (grátis até 1 milhão de requisições/mês em uso
// comercial). Não é segredo — vai em toda URL de tile, visível no navegador.
// Sem ela, cada tile vem com a marca d'água "API KEY REQUIRED".
const CHAVE_CARTO =
  import.meta.env.VITE_CARTO_KEY || "cb1_4emr_1_98b0f4673d1fd558092ece82";

const URL_TILES = `https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png?key=${CHAVE_CARTO}`;

/**
 * Fundo (ruas e bairros) de todos os mapas do app. Fica num lugar só para
 * que trocar de chave ou de fornecedor não exija mexer em cada tela.
 */
export default function FundoMapa() {
  return (
    <TileLayer
      url={URL_TILES}
      attribution="&copy; OpenStreetMap contributors &copy; CARTO"
      subdomains="abcd"
    />
  );
}
