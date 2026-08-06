"""Shape db_process output into template row structures."""

def demuck_result(result):
    res_string = []
    for index, pair in enumerate(result):
        if result[index][1]:
            swaptwopair = '%s%s' % (result[index][0],result[index][1][5])
        else:
            swaptwopair = "££"
        res_dict = {'pattern':pair[0],
                    'first': pair[1],
                    'second':pair[2],
                    'third': pair[3],
                    'swappair': pair[4],
                    'index': pair[5]
                    }
        res_string.append(res_dict)
    return res_string

def demuck_result_list(result):
    res_string = []
    for index, pair in enumerate(result[0]):
        if result[1][index][1]:
            swaptwopair = '%s%s' % (result[1][index][1][0],result[1][index][1][5])
            index_count = result[1][index][4]
        else:
            swaptwopair = "££"
            index_count =  ''
        res_list = [pair,
                    result[1][index][0],
                    result[1][index][1],
                    result[1][index][2],
                    swaptwopair,
                    index_count,
                    ]
        res_string.append(res_list)
    return res_string
