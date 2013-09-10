macro(add_jeolm_sty BASE)
    add_custom_command(
        OUTPUT ${BASE}.dvi ${BASE}.sty
        COMMAND latex
            -output-directory=${CMAKE_CURRENT_BINARY_DIR}
            ${BASE}.dtx
        WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
        DEPENDS ${BASE}.dtx ltxdoc-local.sty
    )
    add_custom_command(
        OUTPUT ${BASE}.pdf
        COMMAND dvipdf ${BASE}.dvi
        WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
        DEPENDS ${BASE}.dvi
    )
    install(
        FILES ${CMAKE_CURRENT_BINARY_DIR}/${BASE}.sty
        DESTINATION "share/texmf/tex/latex/jeolm/"
    )
    install(
        FILES ${CMAKE_CURRENT_BINARY_DIR}/${BASE}.pdf
        DESTINATION "share/texmf/doc/latex/jeolm/"
    )
    set(JEOLM_DTX ${JEOLM_DTX} ${BASE}.dtx)
    set(JEOLM_STY ${JEOLM_STY} ${BASE}.sty)
    set(JEOLM_PDF ${JEOLM_PDF} ${BASE}.pdf)
endmacro(add_jeolm_sty)

add_jeolm_sty(jeolm)
add_jeolm_sty(jeolm-olymp)

add_custom_target(sty ALL DEPENDS ${JEOLM_STY})
add_custom_target(pdf ALL DEPENDS ${JEOLM_PDF})

#subdirs(test)
#
#add_test(latex/test
#    latex
#        -output-directory=${CMAKE_CURRENT_BINARY_DIR}/test
#        -interaction=nonstopmode
#        ${CMAKE_CURRENT_SOURCE_DIR}/test/test.tex
#)
#
#add_test(latex/test/dvipdf
#    dvipdf ${CMAKE_CURRENT_BINARY_DIR}/test/test.dvi
#)

