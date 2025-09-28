import React, { useState } from 'react';

interface Interaction {
  a: string;
  b: string;
  severity: string;
  evidence: string;
  effect: string;
  action: string;
  risk_score: number;
}

const StackChecker: React.FC = () => {
  const [input, setInput] = useState('');
  const [interactions, setInteractions] = useState<Interaction[]>([]);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    const compounds = input.split(',').map(s => s.trim()).filter(Boolean);
    if (compounds.length < 2) {
      setError('Enter at least two compounds separated by commas.');
      return;
    }
    setError(null);
    try {
      const res = await fetch('/api/stack/check', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ compounds }),
      });
      if (!res.ok) {
        const data = await res.json();
        setError(data.detail || 'Error checking interactions.');
        return;
      }
      const data = await res.json();
      setInteractions(data.interactions || []);
    } catch (err) {
      setError('Network error');
    }
  };

  return (
    <div className="p-4">
      <h2 className="text-xl font-semibold mb-2">Stack Checker</h2>
      <textarea
        value={input}
        onChange={(e) => setInput(e.target.value)}
        placeholder="Enter compounds separated by commas e.g. creatine, caffeine, magnesium"
        className="w-full p-2 border rounded mb-2"
        rows={3}
      />
      <button onClick={handleSubmit} className="bg-blue-600 text-white px-4 py-2 rounded">
        Check interactions
      </button>
      {error && <p className="text-red-600 mt-2">{error}</p>}
      {interactions.length > 0 && (
        <div className="mt-4 overflow-auto">
          <table className="min-w-full border">
            <thead>
              <tr className="bg-gray-100">
                <th className="p-2 border">A</th>
                <th className="p-2 border">B</th>
                <th className="p-2 border">Severity</th>
                <th className="p-2 border">Evidence</th>
                <th className="p-2 border">Effect</th>
                <th className="p-2 border">Action</th>
                <th className="p-2 border">Risk Score</th>
              </tr>
            </thead>
            <tbody>
              {interactions.map((inter, idx) => (
                <tr key={idx} className={idx % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                  <td className="p-2 border">{inter.a}</td>
                  <td className="p-2 border">{inter.b}</td>
                  <td className="p-2 border">{inter.severity}</td>
                  <td className="p-2 border">{inter.evidence}</td>
                  <td className="p-2 border">{inter.effect}</td>
                  <td className="p-2 border">{inter.action}</td>
                  <td className="p-2 border">{inter.risk_score.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default StackChecker;
