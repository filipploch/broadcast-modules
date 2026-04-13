
socket.emit('trigger_sequence', { sequence: 'halftime_start', context: {} });

// zatrzymanie konkretnej instancji
socket.emit('stop_sequence', { sequence_id: currentSequenceId });

// zatrzymanie wszystkich instancji danej sekwencji
socket.emit('stop_sequence', { sequence: 'halftime_start' });