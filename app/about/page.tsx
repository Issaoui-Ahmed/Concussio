export default function AboutPage() {
    return (
        <div className="max-w-4xl mx-auto py-12 px-6">
            <h1 className="text-3xl font-bold mb-6 text-[#00417d]">About Us</h1>
            <div className="bg-white p-8 rounded-xl shadow-sm border border-gray-100 space-y-4 text-gray-700 leading-relaxed">
                <p>
                    Welcome to <span className="font-semibold text-[#00417d]">ConcussCare</span>, your trusted assistant for concussion healthcare guidelines and patient support.
                </p>
                <p>
                    Our mission is to bridge the gap between complex medical guidelines and accessible, actionable advice for healthcare professionals, parents, teachers, and coaches. We leverage advanced AI to provide immediate, reliable answers based on the latest pediatric concussion standards.
                </p>
                <p>
                    ConcussCare is designed to help you navigate the recovery process with confidence, ensuring that every decision is informed by verified medical protocols.
                </p>
            </div>
        </div>
    );
}
