export default function SourcesPage() {
    return (
        <div className="max-w-4xl mx-auto py-12 px-6">
            <h1 className="text-3xl font-bold mb-6 text-[#00417d]">Source of Information</h1>
            <div className="bg-white p-8 rounded-xl shadow-sm border border-gray-100 space-y-4 text-gray-700 leading-relaxed">
                <p>
                    The information provided by ConcussCare is grounded in the latest clinical research and standardized guidelines for pediatric concussion management.
                </p>
                <h2 className="text-xl font-semibold text-[#00417d] mt-4">Primary Sources</h2>
                <ul className="list-disc list-inside space-y-2 ml-2">
                    <li>
                        <strong>Living Guideline for Pediatric Concussion Care:</strong> Our system is primarily trained on the comprehensive PedsConcussion guidelines, ensuring adherence to the most current evidence-based practices.
                    </li>
                    <li>
                        <strong>Verified Medical Literature:</strong> We continuously update our knowledge base with peer-reviewed studies and consensus statements from leading sports medicine and neurology organizations.
                    </li>
                </ul>
                <div className="mt-6 p-4 bg-[#e6efff] rounded-lg border border-[#00417d]/20">
                    <p className="text-sm text-[#00417d]">
                        <strong>Disclaimer:</strong> While ConcussCare provides guidance based on established medical protocols, it is not a substitute for professional medical diagnosis or treatment. Always consult with a qualified healthcare provider for individual medical advice.
                    </p>
                </div>
            </div>
        </div>
    );
}
