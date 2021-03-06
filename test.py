#!/usr/bin/env python3

## TODO:
# Output ssc files based on inputs

import music21
import copy

def splitPart(part):
    return music21.stream.Stream([topNotesOf(part), bottomNotesOf(part)])

def topNotesOf(stream):
    new_part = copy.deepcopy(stream).chordify()
    for chord in new_part.recurse().getElementsByClass('Chord'):
        chord.notes = (chord.notes[-1],)
    return new_part.stripTies(retainContainers=True)

def bottomNotesOf(stream):
    new_part = copy.deepcopy(stream).chordify()
    for chord in new_part.recurse().getElementsByClass('Chord'):
        chord.notes = (chord.notes[0],)
    return new_part.stripTies(retainContainers=True)

def expandAllRepeats(stream):
    expanded_parts = [part.expandRepeats() for part in stream.getElementsByClass("Part")]
    return music21.stream.Stream(expanded_parts)

def doubleLength(stream):
    all_doubled = []
    for part in stream.getElementsByClass("Part"):
        measures = part.recurse().getElementsByClass('Measure')
        measures[0].leftBarline = music21.bar.Repeat('start')
        measures[-1].rightBarline = music21.bar.Repeat('end')
        doubled_part = part.expandRepeats()
        for i, m in enumerate(doubled_part.getElementsByClass("Measure")):
            m.number = i
        all_doubled.append(doubled_part)
    return music21.stream.Stream(all_doubled)

def absOffset(note, beat_length):
    return (note.getContextByClass('Measure').offset + note.offset) / beat_length

def fractionalOffset(note, beat_length):
    abs_offset = absOffset(note, beat_length)
    return abs_offset - int(abs_offset)

def lcdOffset(notes, beat_length):
    offsets_in_192nds = [round(fractionalOffset(n, beat_length)*192) for n in notes]
    # Special case
    # Return the number of entries per quarter note duration
    for d in [192, 96, 64, 48, 32, 24, 16, 12, 8, 6, 4, 3, 1]:
        if all(map(lambda nd: nd % d == 0, offsets_in_192nds)):
            return 192//d
    return 1

def getStepArrow(note, key = None):
    if key == None:
        key = note.getContextByClass('Measure').getKeySignatures()[0]
    if note.isChord:
        note = note.notes[0]
    scale_index = (note.pitch.pitchClass - key.getScale().getTonic().pitchClass) % 12
    ##      do di re ri mi fa fi so si la li ti
    return [0, 1, 2, 1, 3, 0, 1, 2, 0, 3,  2, 1][scale_index]

def getMeasureSteps(measure, rows_per_beat = None):
    key = measure.getKeySignatures()[0]
    if rows_per_beat == None:
        rows_per_beat = lcdOffset(measure.notes)
    # Stepmania can't handle anything but measures of 4 :(
    # rowsCount = round(measure.duration.quarterLength * rows_per_beat)
    rowsCount = round(4 * rows_per_beat)
    rows = [['0', '0', '0', '0'] for i in range(rowsCount)]
    for note in measure.notes:
        which_row = round(note.offset * rows_per_beat)
        which_arrow = getStepArrow(note, key)
        rows[which_row][which_arrow] = '1'
    return f"// Measure {measure.number}\n" + \
        "\n".join(["".join(row) for row in rows]) + '\n, '

def joinStepStrings(string1, string2):
    new_string = ""
    for c1, c2 in zip(string1, string2):
        if "2" in [c1, c2]:
            new_string += "2"
        elif "3" in [c1, c2]:
            new_string += "3"
        elif "1" in [c1, c2]:
            new_string += "1"
        else:
            new_string += c1
    return new_string

def getPartStepsString(part):
    string = ""
    part_in_four = part.makeMeasures(meterStream=music21.meter.TimeSignature('4/4'))
    for measure in part_in_four.recurse().getElementsByClass('Measure'):
        string += getMeasureSteps(measure)
    return string

def setRowCol(all_rows, row, col, value):
    while len(all_rows) <= row:
        all_rows.append(['0', '0', '0', '0'])
    all_rows[row][col] = value

def getRowCol(all_rows, row, col):
    if len(all_rows) <= row:
        return '0'
    return all_rows[row][col]

def setNoteInRows(all_rows, rows_per_beat, note, beat_length = 1):
    row = round(absOffset(note, beat_length) * rows_per_beat)
    arrow = getStepArrow(note)
    if note.duration.quarterLength <= 2:
        if getRowCol(all_rows, row, arrow) == '0':
            setRowCol(all_rows, row, arrow, '1')
    else:
        setRowCol(all_rows, row, arrow, '2')
        end_row = round((absOffset(note, beat_length) + note.duration.quarterLength / beat_length - .6) * rows_per_beat)
        if getRowCol(all_rows, end_row, arrow) in ['0', '1']:
            setRowCol(all_rows, end_row, arrow, '3')

def rowsToString(all_rows, rows_per_beat):
    string = ""
    rows_per_measure = rows_per_beat * 4
    while not len(all_rows) % rows_per_measure == 0:
        all_rows.append(['0', '0','0', '0'])
    for i in range(0, len(all_rows), rows_per_measure):
        string += "\n".join(["".join(r) for r in all_rows[i : i + rows_per_measure]]) + ",\n"
    return string[:-2]

def replaceOverlappedHoldStartsWithTaps(rows):
    for col in range(4):
        start_index = None
        for i, r in enumerate(rows):
            if start_index == None:
                if r[col] == '2':
                    start_index = i
                elif r[col] == '3':
                    r[col] == '0'
            else:
                if r[col] == '1':
                    rows[start_index][col] = '1'
                    start_index = None
                elif r[col] == '2':
                    rows[start_index][col] = '1'
                    start_index = i
                elif r[col] == '3':
                    start_index = None

def getPartRowsWithHolds(item, rows_per_beat, beat_length = 1):
    string = ""
    all_notes = []
    all_rows = []
    for measure in item.recurse().getElementsByClass('Measure'):
        all_notes.extend(measure.notes)
    for note in all_notes:
        setNoteInRows(all_rows, rows_per_beat, note, beat_length = beat_length)
    replaceOverlappedHoldStartsWithTaps(all_rows)
    return all_rows

def getRowsPerBeat(item, beat_length):
    if isinstance(item, music21.stream.Measure):
        return lcdOffset(item.notes, beat_length)
    else:
        all_notes = []
        for measure in item.recurse().getElementsByClass('Measure'):
            all_notes.extend(measure.notes)
        return lcdOffset(all_notes, beat_length)


def getMeasureTimeSigString(measure):
    return f"{measure.offset}={int(measure.duration.quarterLength)}=4,\n"

def getPartTimeSigString(part):
    string = ""
    for measure in part.recurse().getElementsByClass('Measure'):
        string += getMeasureTimeSigString(measure)
    return string[:-2]

def getPartBpmString(part, beat_length = 1):
    string=""
    for mark in part.recurse().getElementsByClass('MetronomeMark'):
        offset = mark.activeSite.offset + mark.offset
        string += f"{offset}={mark.getQuarterBPM() / beat_length},\n"
    if len(string) > 0:
        return string[:-2]
    else:
        return "0.0=120.0"

def getBeatLength(item):
    time_signature = item.recurse().getElementsByClass('TimeSignature')[0]
    if time_signature.denominator == 8 and time_signature.numerator % 3 == 0:
        return 1.5
    return 1

def getPartTime(part):
    beat_length = getBeatLength(part)
    last_measure = part.recurse().getElementsByClass('Measure')[-1]
    total_offset = last_measure.offset + last_measure.duration.quarterLength
    accumulated_time = 0.0
    previous_offset = 0
    for mark in part.recurse().getElementsByClass('MetronomeMark'):
        offset = mark.activeSite.offset + mark.offset
        accumulated_time += (offset - previous_offset) * (60 / mark.getQuarterBPM()) / beat_length
        previous_offset = offset
    accumulated_time += (total_offset - previous_offset) * (60 / mark.getQuarterBPM()) / beat_length
    return accumulated_time

def estimateDifficultyMeter(rows_string, part):
    time = getPartTime(part)
    taps = rows_string.count("1")
    holds = rows_string.count("2")
    total_moves = taps + holds * 2
    moves_per_second = total_moves / time
    return round(moves_per_second * 2 - 1)

def loadXml(path):
    return music21.converter.parse(path)
