import NavBar from "@/components/nav-bar";
import CTA from "@/components/cta";

export default function HomePage() {
  const activePage: string = "Hem"; // This is the home page, so "Hem" is active

  return (
    <div className="min-h-screen flex flex-col">
      <NavBar activePage={activePage} />

      <main className="flex-grow bg-gradient-to-br from-blue-100 via-indigo-50 to-white flex flex-col items-center justify-center p-4 sm:p-8 text-gray-800">
        <div className="w-full max-w-4xl mx-auto text-center space-y-6 sm:space-y-8">
          {/* Hero Section */}
          <section>
            <h1 className="text-4xl sm:text-5xl md:text-6xl lg:text-7xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-500 to-indigo-600 pb-4 leading-tight">
              Valkompass.ai
            </h1>
            <p className="text-lg sm:text-xl md:text-2xl font-medium bg-clip-text text-transparent bg-gradient-to-r from-gray-700 to-gray-900 mt-4 sm:mt-6 max-w-2xl mx-auto leading-relaxed px-2">
              Vi samlar partiernas åsikter och beslut – du ställer frågorna!
            </p>
          </section>

          {/* How it Works Section */}
          <section className="py-8 sm:py-12">
            <h2 className="text-2xl sm:text-3xl md:text-4xl lg:text-5xl font-semibold text-gray-800 mb-6 sm:mb-8 leading-tight">
              Hur det funkar
            </h2>
            <div className="space-y-4 sm:space-y-6">
              <p className="text-base sm:text-lg md:text-xl text-gray-600 max-w-2xl mx-auto leading-relaxed px-2">
                Valkompass.ai samlar in partiernas officiella dokument, som partiprogram, valmanifest, voteringshistorik, riksdagsutlåtanden, arbetsgruppsrapporter och andra protokoll från offentliga sammanhang.
              </p>
              <p className="text-base sm:text-lg md:text-xl text-gray-600 max-w-2xl mx-auto leading-relaxed px-2">
                Dessa dokument används av en AI-modell (OpenAI GPT-5.6 Luna) som analyserar innehållet och gör det möjligt för dig att ställa frågor och föra samtal med partiernas ståndpunkter som grund.
              </p>
              <p className="text-base sm:text-lg text-gray-600 max-w-2xl mx-auto leading-relaxed px-2 pt-4">
                Allt vi gör är open source. För kod och mer information, <a href="https://github.com/valkompass-ai/valkompass-ai" className="text-blue-500 hover:text-blue-600 underline touch-manipulation" target="_blank" rel="noopener noreferrer">besök vårt GitHub-repo</a>.
              </p>
            </div>
          </section>
          <CTA />
        </div>
      </main>
    </div>
  );
}
